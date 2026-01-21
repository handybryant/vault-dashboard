"""Hyperliquid Vault Dashboard - Streamlit Application."""

import time
import pandas as pd
import streamlit as st

from config import DEFAULT_TOP_N, REFRESH_INTERVAL_SECONDS
from vault_api import get_top_vaults_with_details, get_all_vaults


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

def main():
    st.set_page_config(
        page_title="Hyperliquid Vault Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("Hyperliquid Vault Dashboard")

    # Add a placeholder for the last update time
    status_placeholder = st.empty()

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

    # Auto-refresh
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
