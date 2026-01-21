"""Hyperliquid Vault Dashboard - Streamlit Application."""

import time
from datetime import datetime
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

from config import DEFAULT_TOP_N, REFRESH_INTERVAL_SECONDS
from vault_api import get_top_vaults_with_details, get_all_vaults
from metrics import format_ratio, format_drawdown


def truncate_address(address: str) -> str:
    """Truncate address to 0x1234...abcd format."""
    if not address or len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"


def format_currency(value: float | None) -> str:
    """Format value as currency with $ sign."""
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.2f}K"
    return f"${value:,.2f}"


def format_percentage(value: float | None) -> str:
    """Format decimal as percentage."""
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def format_pnl(value: float | None) -> float | None:
    """Format PnL as a plain number for reliable sorting."""
    if value is None:
        return None
    return round(value, 2)


def create_vault_csv(vault: Dict[str, Any]) -> str:
    """Create CSV content for a single vault's daily returns."""
    daily_returns = vault.get("daily_returns", [])

    lines = ["date,period_return,cumulative_return,timestamp"]

    cumulative = 0.0
    for ts, ret in daily_returns:
        cumulative += ret
        date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{date_str},{ret:.8f},{cumulative:.8f},{ts}")

    return "\n".join(lines)


def create_bulk_csv(vaults: List[Dict[str, Any]]) -> str:
    """Create CSV content for all vaults' returns."""
    lines = ["vault_name,vault_address,date,period_return,cumulative_return,timestamp"]

    for vault in vaults:
        name = vault.get("name", "Unknown").replace(",", " ")
        address = vault.get("vaultAddress", "")
        daily_returns = vault.get("daily_returns", [])

        cumulative = 0.0
        for ts, ret in daily_returns:
            cumulative += ret
            date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"{name},{address},{date_str},{ret:.8f},{cumulative:.8f},{ts}")

    return "\n".join(lines)


def sanitize_filename(name: str) -> str:
    """Sanitize vault name for use in filename."""
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()


def main():
    st.set_page_config(
        page_title="Hyperliquid Vault Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("Hyperliquid Vault Dashboard")

    # Add a placeholder for the last update time
    status_placeholder = st.empty()

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("Refresh now"):
            st.rerun()

    # Fetch data
    with st.spinner("Fetching vault data..."):
        try:
            # Check if vaultSummaries API returns data
            all_vaults = get_all_vaults()
            using_fallback = len(all_vaults) == 0

            vaults = get_top_vaults_with_details(DEFAULT_TOP_N)

            if using_fallback:
                st.info("Note: vaultSummaries API returned empty. Showing known vaults only (HLP).")

            status_placeholder.success(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')} - Showing {len(vaults)} vault(s)")
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            time.sleep(REFRESH_INTERVAL_SECONDS)
            st.rerun()
            return

    st.caption(f"Auto-refreshes every {REFRESH_INTERVAL_SECONDS} seconds")

    if not vaults:
        st.warning("No vault data available.")
    else:
        # Bulk download button
        st.subheader("Export Data")
        bulk_csv = create_bulk_csv(vaults)
        st.download_button(
            label="Download All Vaults Returns (CSV)",
            data=bulk_csv,
            file_name="all_vaults_returns.csv",
            mime="text/csv",
            key="bulk_download"
        )

        st.subheader("Vault Performance")

        # Create DataFrame for display
        df = pd.DataFrame(vaults)

        # Format columns for display
        display_df = pd.DataFrame({
            "Vault Name": df["name"],
            "Leader Address": df["leader"].apply(truncate_address),
            "TVL": df["tvl"],
            "Leader %": df["leader_fraction"].apply(format_percentage),
            "30d PnL": df["month_pnl"].apply(format_pnl),
            "All-time PnL": df["alltime_pnl"].apply(format_pnl),
            "30d R/V": df["rv_30d"].apply(format_ratio),
            "1Y R/V": df["rv_1y"].apply(format_ratio),
            "All-Time R/V": df["rv_alltime"].apply(format_ratio),
            "Max DD": df["max_drawdown"].apply(format_drawdown),
        })

        # Display the table
        display_df["TVL"] = pd.to_numeric(display_df["TVL"], errors="coerce")
        display_df["30d PnL"] = pd.to_numeric(display_df["30d PnL"], errors="coerce")
        display_df["All-time PnL"] = pd.to_numeric(display_df["All-time PnL"], errors="coerce")

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=750,
            column_config={
                "TVL": st.column_config.NumberColumn(format="localized", step=0.01),
                "30d PnL": st.column_config.NumberColumn(format="localized", step=0.01),
                "All-time PnL": st.column_config.NumberColumn(format="localized", step=0.01),
            },
        )

        # Per-vault download section
        st.subheader("Individual Vault Downloads")
        st.caption("Download daily returns data for specific vaults")

        # Create columns for download buttons (4 per row)
        cols_per_row = 4
        for i in range(0, len(vaults), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(vaults):
                    vault = vaults[idx]
                    vault_name = vault.get("name", "Unknown")
                    daily_returns = vault.get("daily_returns", [])

                    with col:
                        if daily_returns:
                            csv_data = create_vault_csv(vault)
                            filename = f"{sanitize_filename(vault_name)}_returns.csv"
                            st.download_button(
                                label=f"{vault_name[:20]}...",
                                data=csv_data,
                                file_name=filename,
                                mime="text/csv",
                                key=f"download_{idx}",
                                help=f"Download daily returns for {vault_name}"
                            )
                        else:
                            st.button(
                                f"{vault_name[:20]}...",
                                disabled=True,
                                key=f"no_data_{idx}",
                                help="No return data available"
                            )

    # Auto-refresh
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
