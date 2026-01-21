"""Hyperliquid Vault API client functions."""

import requests
from typing import List, Dict, Any, Optional, Iterable

from config import API_URL, DEFAULT_TOP_N, VAULT_DEX, VAULT_DEX_FALLBACKS, STATS_VAULTS_URL
from metrics import get_vault_metrics

# Known vault addresses as fallback when vaultSummaries returns empty
KNOWN_VAULT_ADDRESSES = [
    "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303",  # HLP - Hyperliquidity Provider
]


def _post_info(payload: Dict[str, Any]) -> Any:
    response = requests.post(API_URL, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def _extract_vault_list(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("vaultSummaries", "vaults", "data", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []

def _extract_stats_vaults(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, list):
        return []
    vaults = []
    for item in data:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary") or {}
        vault_address = summary.get("vaultAddress")
        if not vault_address:
            continue
        tvl_raw = summary.get("tvl")
        try:
            tvl = float(tvl_raw) if tvl_raw is not None else 0.0
        except (TypeError, ValueError):
            tvl = 0.0
        vaults.append({
            "name": summary.get("name", "Unknown"),
            "leader": summary.get("leader", ""),
            "vaultAddress": vault_address,
            "tvl": tvl,
            "pnls": item.get("pnls"),
        })
    return vaults


def _iter_dex_candidates(primary: Optional[str], fallbacks: Iterable[str]) -> List[Optional[str]]:
    candidates: List[Optional[str]] = []
    if primary:
        candidates.append(primary)
    for dex in fallbacks:
        if dex and dex not in candidates:
            candidates.append(dex)
    if not candidates:
        candidates.append(None)
    return candidates


def get_all_vaults() -> List[Dict[str, Any]]:
    """Fetch all vault summaries from Hyperliquid API.

    Returns:
        List of vault summary dictionaries containing name, leader, tvl, etc.
    """
    # Prefer the stats vaults feed (used by the UI) to avoid empty vaultSummaries.
    try:
        response = requests.get(STATS_VAULTS_URL, timeout=10)
        response.raise_for_status()
        vaults = _extract_stats_vaults(response.json())
        if vaults:
            return vaults
    except requests.RequestException:
        pass

    for dex in _iter_dex_candidates(VAULT_DEX, VAULT_DEX_FALLBACKS):
        payload = {"type": "vaultSummaries"}
        if dex:
            payload["dex"] = dex
        try:
            data = _post_info(payload)
        except requests.RequestException:
            continue
        vaults = _extract_vault_list(data)
        if vaults:
            return vaults
    return []


def get_vault_details(vault_address: str) -> Optional[Dict[str, Any]]:
    """Fetch detailed information for a specific vault.

    Args:
        vault_address: The vault's address (0x...)

    Returns:
        Vault details dictionary or None if not found.
    """
    for dex in _iter_dex_candidates(VAULT_DEX, VAULT_DEX_FALLBACKS):
        payload = {"type": "vaultDetails", "vaultAddress": vault_address}
        if dex:
            payload["dex"] = dex
        try:
            return _post_info(payload)
        except requests.RequestException:
            continue
    return None


def extract_pnl(portfolio: List[List[Any]], period: str) -> Optional[float]:
    """Extract the latest PnL value from a portfolio period.

    Args:
        portfolio: List of [period_name, period_data] tuples from vault details
        period: Either "month" for 30-day or "allTime" for all-time

    Returns:
        The latest cumulative PnL value or None if unavailable.
    """
    if not portfolio:
        return None

    # Portfolio is a list of [period_name, period_data] tuples
    period_data = None
    for item in portfolio:
        if isinstance(item, list) and len(item) >= 2 and item[0] == period:
            period_data = item[1]
            break

    if not period_data:
        return None

    pnl_history = period_data.get("pnlHistory", [])
    if not pnl_history:
        return None

    # Get the last entry which contains the cumulative PnL
    # pnlHistory is an array of [timestamp, pnl_value] tuples
    last_entry = pnl_history[-1]
    if isinstance(last_entry, list) and len(last_entry) >= 2:
        return float(last_entry[1])

    return None

def extract_stats_pnl(pnls: Any, period: str) -> Optional[float]:
    """Extract the latest PnL value from the stats vault list."""
    if not isinstance(pnls, list):
        return None
    for item in pnls:
        if not isinstance(item, list) or len(item) < 2:
            continue
        if item[0] != period:
            continue
        series = item[1]
        if not isinstance(series, list) or not series:
            return None
        try:
            return float(series[-1])
        except (TypeError, ValueError):
            return None
    return None


def get_vault_from_details(vault_address: str) -> Optional[Dict[str, Any]]:
    """Build vault summary from vault details when vaultSummaries is unavailable.

    Args:
        vault_address: The vault's address (0x...)

    Returns:
        Vault dictionary with enriched data or None if fetch fails.
    """
    try:
        details = get_vault_details(vault_address)
        if not details:
            return None

        portfolio = details.get("portfolio", [])

        # Extract TVL from the latest account value in the portfolio
        tvl = 0.0
        for item in portfolio:
            if isinstance(item, list) and len(item) >= 2:
                period_data = item[1]
                if period_data and "accountValueHistory" in period_data:
                    history = period_data["accountValueHistory"]
                    if history:
                        tvl = float(history[-1][1])
                        break

        return {
            "name": details.get("name", "Unknown"),
            "leader": details.get("leader", ""),
            "vaultAddress": vault_address,
            "tvl": tvl,
            "leader_fraction": details.get("leaderFraction"),
            "portfolio": portfolio,
        }
    except Exception:
        return None


def get_top_vaults_with_details(n: int = DEFAULT_TOP_N) -> List[Dict[str, Any]]:
    """Fetch top N vaults by TVL with detailed information.

    Args:
        n: Number of top vaults to fetch (default 20)

    Returns:
        List of vault dictionaries with combined summary and detail data.
    """
    # Get all vault summaries
    vaults = get_all_vaults()

    # If vaultSummaries returns empty, use known vault addresses as fallback
    if not vaults:
        vaults = []
        for addr in KNOWN_VAULT_ADDRESSES:
            vault_data = get_vault_from_details(addr)
            if vault_data:
                vaults.append(vault_data)

    # Sort by TVL descending and take top N
    sorted_vaults = sorted(
        vaults,
        key=lambda v: float(v.get("tvl", 0)),
        reverse=True
    )[:n]

    # Enrich each vault with details
    enriched_vaults = []
    for vault in sorted_vaults:
        vault_address = vault.get("vaultAddress")
        if not vault_address:
            continue

        pnls = vault.get("pnls")
        # Check if we already have portfolio data (from fallback path)
        portfolio = vault.get("portfolio")
        leader_fraction = vault.get("leader_fraction")

        if portfolio is None:
            details = get_vault_details(vault_address)
            if details:
                leader_fraction = details.get("leaderFraction")
                portfolio = details.get("portfolio")

        # Extract PnL data from stats list if available, otherwise from portfolio.
        month_pnl = extract_stats_pnl(pnls, "month") if pnls else None
        alltime_pnl = extract_stats_pnl(pnls, "allTime") if pnls else None
        if month_pnl is None or alltime_pnl is None:
            month_pnl = month_pnl if month_pnl is not None else extract_pnl(portfolio, "month")
            alltime_pnl = alltime_pnl if alltime_pnl is not None else extract_pnl(portfolio, "allTime")

        # Calculate custom metrics from portfolio data
        metrics = get_vault_metrics(portfolio) if portfolio else {}

        enriched_vaults.append({
            "name": vault.get("name", "Unknown"),
            "vaultAddress": vault_address,
            "leader": vault.get("leader", ""),
            "tvl": float(vault.get("tvl", 0)),
            "leader_fraction": float(leader_fraction) if leader_fraction else None,
            "month_pnl": month_pnl,
            "alltime_pnl": alltime_pnl,
            "rv_30d": metrics.get("rv_30d"),
            "rv_1y": metrics.get("rv_1y"),
            "rv_alltime": metrics.get("rv_alltime"),
            "max_drawdown": metrics.get("max_drawdown"),
            "daily_returns": metrics.get("daily_returns", []),
            "weekly_returns": metrics.get("weekly_returns", []),
        })

    return enriched_vaults
