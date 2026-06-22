from __future__ import annotations

from quanthack.backtesting.portfolio_allocator import AllocationPolicy


ALLOCATION_PROFILE_DEFAULT = "default"
ALLOCATION_PROFILE_DIRECTIONAL_PROBE = "directional_probe"
ALLOCATION_PROFILE_NAMES = (
    ALLOCATION_PROFILE_DEFAULT,
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
)


def allocation_policy_for_strategy(
    strategy_name: str,
    config,
    *,
    profile: str = ALLOCATION_PROFILE_DEFAULT,
) -> AllocationPolicy | None:
    if profile == ALLOCATION_PROFILE_DIRECTIONAL_PROBE:
        return directional_probe_allocation_policy(config)
    if profile != ALLOCATION_PROFILE_DEFAULT:
        raise ValueError(f"unknown allocation profile: {profile}")
    if strategy_name == "opportunity_probe":
        return opportunity_probe_allocation_policy(config)
    return None


def opportunity_probe_allocation_policy(config) -> AllocationPolicy:
    return AllocationPolicy(
        max_gross_leverage=config.risk.max_gross_leverage,
        max_symbol_gross_pct=config.risk.max_symbol_notional_pct,
        max_net_directional_pct=1.0,
        max_forex_gross_pct=0.80,
        max_metal_gross_pct=0.25,
        max_crypto_gross_pct=0.40,
        min_active_symbols=1,
        min_position_notional_usd=500.0,
        apply_diversification_scale=False,
        min_rebalance_notional_usd=250.0,
        min_rebalance_change_pct=0.02,
    )


def directional_probe_allocation_policy(config) -> AllocationPolicy:
    """Bounded single-signal policy for live recovery diagnostics/probes."""

    return AllocationPolicy(
        max_gross_leverage=min(config.risk.max_gross_leverage, 0.50),
        max_symbol_gross_pct=min(config.risk.max_symbol_notional_pct, 0.10),
        max_net_directional_pct=1.0,
        max_forex_gross_pct=0.30,
        max_metal_gross_pct=0.10,
        max_crypto_gross_pct=0.10,
        min_active_symbols=1,
        min_position_notional_usd=500.0,
        apply_diversification_scale=False,
        min_rebalance_notional_usd=250.0,
        min_rebalance_change_pct=0.02,
    )
