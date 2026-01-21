"""Hyperliquid Vault API client functions."""

import requests
from typing import List, Dict, Any, Optional

from config import API_URL, DEFAULT_TOP_N

# Known vault addresses as fallback when vaultSummaries returns empty
KNOWN_VAULT_ADDRESSES = [
    "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303",  # HLP - Hyperliquidity Provider
]


def get_all_vaults() -> List[Dict[str, Any]]:
    """Fetch all vault summaries from Hyperliquid API.

    Returns:
        List of vault summary dictionaries containing name, leader, tvl, etc.
    """
    response = requests.post(API_URL, json={"type": "vaultSummaries"})
    response.raise_for_status()
    return response.json()


def get_vault_details(vault_address: str) -> Optional[Dict[str, Any]]:
    """Fetch detailed information for a specific vault.

    Args:
        vault_address: The vault's address (0x...)

    Returns:
        Vault details dictionary or None if not found.
    """
    response = requests.post(
        API_URL,
        json={"type": "vaultDetails", "vaultAddress": vault_address}
    )
    response.raise_for_status()
    return response.json()


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

        # Check if we already have portfolio data (from fallback path)
        portfolio = vault.get("portfolio")
        leader_fraction = vault.get("leader_fraction")

        if portfolio is None:
            details = get_vault_details(vault_address)
            if details:
                leader_fraction = details.get("leaderFraction")
                portfolio = details.get("portfolio")

        # Extract PnL data from portfolio
        month_pnl = extract_pnl(portfolio, "month")
        alltime_pnl = extract_pnl(portfolio, "allTime")

        enriched_vaults.append({
            "name": vault.get("name", "Unknown"),
            "leader": vault.get("leader", ""),
            "tvl": float(vault.get("tvl", 0)),
            "leader_fraction": float(leader_fraction) if leader_fraction else None,
            "month_pnl": month_pnl,
            "alltime_pnl": alltime_pnl,
        })

    return enriched_vaults
