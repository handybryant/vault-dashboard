"""Custom risk-adjusted performance metrics for vault analysis."""

import math
from typing import List, Tuple, Optional, Dict, Any

# Type aliases for clarity
TimeSeries = List[List[Any]]  # [[timestamp, value], ...]
ReturnSeries = List[Tuple[int, float]]  # [(timestamp, return), ...]


def calculate_period_returns(
    acct_history: TimeSeries,
    pnl_history: TimeSeries
) -> ReturnSeries:
    """Calculate period returns from account value and PnL history.

    Formula: return_t = (pnl_t - pnl_{t-1}) / tvl_{t-1}
    This represents the return a $1 depositor would earn each period.

    Args:
        acct_history: [[timestamp, TVL], ...] - Total vault value over time
        pnl_history: [[timestamp, cumulative_pnl], ...] - Cumulative PnL

    Returns:
        List of (timestamp, period_return) tuples
    """
    if not acct_history or not pnl_history or len(pnl_history) < 2:
        return []

    # Build lookup for TVL by timestamp
    tvl_by_time: Dict[int, float] = {}
    for entry in acct_history:
        if isinstance(entry, list) and len(entry) >= 2:
            try:
                ts = int(entry[0])
                tvl = float(entry[1])
                tvl_by_time[ts] = tvl
            except (TypeError, ValueError):
                continue

    # Sort PnL history by timestamp
    sorted_pnl = []
    for entry in pnl_history:
        if isinstance(entry, list) and len(entry) >= 2:
            try:
                ts = int(entry[0])
                pnl = float(entry[1])
                sorted_pnl.append((ts, pnl))
            except (TypeError, ValueError):
                continue
    sorted_pnl.sort(key=lambda x: x[0])

    if len(sorted_pnl) < 2:
        return []

    returns: ReturnSeries = []

    for i in range(1, len(sorted_pnl)):
        ts_prev, pnl_prev = sorted_pnl[i - 1]
        ts_curr, pnl_curr = sorted_pnl[i]

        # Get TVL at previous timestamp (or closest available)
        tvl_prev = tvl_by_time.get(ts_prev)
        if tvl_prev is None:
            # Find closest TVL timestamp before or at ts_prev
            closest_ts = None
            for ts in tvl_by_time:
                if ts <= ts_prev:
                    if closest_ts is None or ts > closest_ts:
                        closest_ts = ts
            if closest_ts is not None:
                tvl_prev = tvl_by_time[closest_ts]

        if tvl_prev is None or tvl_prev <= 0:
            continue

        period_return = (pnl_curr - pnl_prev) / tvl_prev
        returns.append((ts_curr, period_return))

    return returns


def calculate_cumulative_returns(returns: ReturnSeries) -> ReturnSeries:
    """Calculate cumulative returns from period returns.

    Args:
        returns: List of (timestamp, period_return) tuples

    Returns:
        List of (timestamp, cumulative_return) tuples
    """
    if not returns:
        return []

    cumulative: ReturnSeries = []
    cum_return = 0.0

    for ts, ret in returns:
        cum_return += ret
        cumulative.append((ts, cum_return))

    return cumulative


def calculate_return_volatility_ratio(
    returns: ReturnSeries,
    periods_per_year: int,
    min_periods: int = 4
) -> Optional[float]:
    """Calculate annualized return/volatility ratio (Sharpe-like without risk-free rate).

    Formula:
        annualized_return = mean(returns) * periods_per_year
        annualized_vol = std(returns) * sqrt(periods_per_year)
        ratio = annualized_return / annualized_vol

    Args:
        returns: List of (timestamp, return) tuples
        periods_per_year: Annualization factor (252 for daily, 52 for weekly)
        min_periods: Minimum number of periods required

    Returns:
        Return/volatility ratio or None if insufficient data
    """
    if not returns or len(returns) < min_periods:
        return None

    return_values = [r[1] for r in returns]
    n = len(return_values)

    # Calculate mean
    mean_return = sum(return_values) / n

    # Calculate standard deviation (sample std with n-1)
    if n < 2:
        return None

    variance = sum((r - mean_return) ** 2 for r in return_values) / (n - 1)
    std_return = math.sqrt(variance)

    if std_return == 0:
        return None

    # Annualize
    annualized_return = mean_return * periods_per_year
    annualized_vol = std_return * math.sqrt(periods_per_year)

    return annualized_return / annualized_vol


def calculate_max_drawdown(returns: ReturnSeries) -> Optional[float]:
    """Calculate maximum drawdown from cumulative return series.

    Formula: max(peak - trough) / peak over all time

    Args:
        returns: List of (timestamp, period_return) tuples

    Returns:
        Maximum drawdown as a positive percentage, or None if insufficient data
    """
    if not returns:
        return None

    # Calculate cumulative returns (compounding)
    cumulative_values = []
    cum_value = 1.0  # Start with $1

    for ts, ret in returns:
        cum_value *= (1 + ret)
        cumulative_values.append(cum_value)

    if not cumulative_values:
        return None

    # Calculate drawdown at each point
    max_drawdown = 0.0
    peak = cumulative_values[0]

    for value in cumulative_values:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

    return max_drawdown


def extract_period_data(portfolio: List[Any], period: str) -> Optional[Dict[str, Any]]:
    """Extract data for a specific period from portfolio.

    Args:
        portfolio: List of [period_name, period_data] tuples from vault details
        period: "day", "month", or "allTime"

    Returns:
        Period data dictionary or None if not found
    """
    if not portfolio:
        return None

    for item in portfolio:
        if isinstance(item, list) and len(item) >= 2 and item[0] == period:
            return item[1] if isinstance(item[1], dict) else None

    return None


def get_vault_metrics(portfolio: List[Any]) -> Dict[str, Any]:
    """Calculate all custom metrics for a vault.

    Args:
        portfolio: Portfolio data from vault details API

    Returns:
        Dictionary with calculated metrics
    """
    metrics: Dict[str, Any] = {
        "rv_30d": None,
        "rv_1y": None,
        "rv_alltime": None,
        "max_drawdown": None,
        "daily_returns": [],
        "weekly_returns": [],
    }

    # 30-day Return/Volatility (from month data, daily granularity)
    month_data = extract_period_data(portfolio, "month")
    if month_data:
        acct_history = month_data.get("accountValueHistory", [])
        pnl_history = month_data.get("pnlHistory", [])
        daily_returns = calculate_period_returns(acct_history, pnl_history)

        if daily_returns:
            metrics["daily_returns"] = daily_returns
            # Require minimum 7 days of data for 30-day metric
            metrics["rv_30d"] = calculate_return_volatility_ratio(
                daily_returns,
                periods_per_year=252,
                min_periods=7
            )

    # 1-Year and All-Time R/V (from allTime data, weekly granularity)
    alltime_data = extract_period_data(portfolio, "allTime")
    if alltime_data:
        acct_history = alltime_data.get("accountValueHistory", [])
        pnl_history = alltime_data.get("pnlHistory", [])
        weekly_returns = calculate_period_returns(acct_history, pnl_history)

        if weekly_returns:
            metrics["weekly_returns"] = weekly_returns

            # All-time R/V (minimum 4 weeks)
            metrics["rv_alltime"] = calculate_return_volatility_ratio(
                weekly_returns,
                periods_per_year=52,
                min_periods=4
            )

            # 1-Year R/V (require minimum 52 weeks of data)
            if len(weekly_returns) >= 52:
                # Use only the last 52 weeks
                last_52_weeks = weekly_returns[-52:]
                metrics["rv_1y"] = calculate_return_volatility_ratio(
                    last_52_weeks,
                    periods_per_year=52,
                    min_periods=52
                )

            # Max drawdown from all-time data
            metrics["max_drawdown"] = calculate_max_drawdown(weekly_returns)

    return metrics


def format_ratio(value: Optional[float]) -> str:
    """Format return/volatility ratio for display."""
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def format_drawdown(value: Optional[float]) -> str:
    """Format max drawdown as percentage for display."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"
