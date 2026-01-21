"""Vault Detail Page - Shows cumulative returns chart."""

from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Vault Detail",
    page_icon="📈",
    layout="wide",
)


def main():
    # Check if vault data is in session state
    if "selected_vault" not in st.session_state:
        st.warning("No vault selected. Please go back to the dashboard and select a vault.")
        if st.button("Go to Dashboard"):
            st.switch_page("app.py")
        return

    vault = st.session_state.selected_vault
    vault_name = vault.get("name", "Unknown Vault")

    st.title(f"📈 {vault_name}")
    st.caption(f"Vault Address: {vault.get('vaultAddress', 'N/A')}")

    # Get the weekly returns for all-time chart (from allTime data)
    weekly_returns = vault.get("weekly_returns", [])

    if not weekly_returns:
        st.warning("No historical return data available for this vault.")
        if st.button("Back to Dashboard"):
            st.switch_page("app.py")
        return

    # Calculate cumulative returns
    dates = []
    cumulative_returns = []
    cumulative = 0.0

    for ts, ret in weekly_returns:
        cumulative += ret
        date = datetime.fromtimestamp(ts / 1000)
        dates.append(date)
        cumulative_returns.append(cumulative * 100)  # Convert to percentage

    # Create Plotly chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates,
        y=cumulative_returns,
        mode='lines',
        name='Cumulative Return',
        line=dict(color='#00D4AA', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 212, 170, 0.1)',
    ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        title=dict(
            text=f"All-Time Cumulative Returns - {vault_name}",
            font=dict(size=20),
        ),
        xaxis_title="Date",
        yaxis_title="Cumulative Return (%)",
        template="plotly_dark",
        hovermode="x unified",
        showlegend=False,
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='rgba(128, 128, 128, 0.2)',
    )

    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='rgba(128, 128, 128, 0.2)',
        ticksuffix="%",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Display summary stats
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Return", f"{cumulative_returns[-1]:.2f}%" if cumulative_returns else "N/A")

    with col2:
        max_return = max(cumulative_returns) if cumulative_returns else 0
        st.metric("Peak Return", f"{max_return:.2f}%")

    with col3:
        max_dd = vault.get("max_drawdown")
        st.metric("Max Drawdown", f"{max_dd * 100:.1f}%" if max_dd is not None else "N/A")

    with col4:
        data_points = len(weekly_returns)
        st.metric("Data Points", f"{data_points} weeks")

    st.divider()

    if st.button("Back to Dashboard"):
        st.switch_page("app.py")


if __name__ == "__main__":
    main()
