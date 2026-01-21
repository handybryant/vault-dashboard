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


def format_pnl(value: float | None) -> str:
    """Format PnL with color indicator."""
    if value is None:
        return "N/A"
    formatted = format_currency(value)
    return formatted


def main():
    st.set_page_config(
        page_title="Hyperliquid Vault Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("Hyperliquid Vault Dashboard")

    # Add a placeholder for the last update time
    status_placeholder = st.empty()

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
            "TVL": df["tvl"].apply(format_currency),
            "Leader %": df["leader_fraction"].apply(format_percentage),
            "30d PnL": df["month_pnl"].apply(format_pnl),
            "All-time PnL": df["alltime_pnl"].apply(format_pnl),
        })

        # Display the table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=750,
        )

    # Auto-refresh
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
