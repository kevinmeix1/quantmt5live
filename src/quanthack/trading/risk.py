from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from quanthack.core.clock import CompetitionMode


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class RiskState(StrEnum):
    NORMAL = "NORMAL"
    REDUCE_ONLY = "REDUCE_ONLY"
    FROZEN = "FROZEN"


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    starting_equity: float = 1_000_000.0
    day_start_equity: float = 1_000_000.0
    peak_equity: float = 1_000_000.0
    margin_level_pct: float | None = None

    def __post_init__(self) -> None:
        values = [self.equity, self.starting_equity, self.day_start_equity, self.peak_equity]
        if any(not isfinite(value) or value <= 0 for value in values):
            raise ValueError("equity values must be positive finite numbers")

        if self.margin_level_pct is not None and self.margin_level_pct <= 0:
            raise ValueError("margin_level_pct must be positive when provided")

    @property
    def total_pnl_pct(self) -> float:
        return (self.equity / self.starting_equity) - 1.0

    @property
    def daily_pnl_pct(self) -> float:
        return (self.equity / self.day_start_equity) - 1.0

    @property
    def drawdown_pct(self) -> float:
        return max(0.0, 1.0 - (self.equity / self.peak_equity))


@dataclass(frozen=True)
class Position:
    symbol: str
    notional_usd: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    positions: tuple[Position, ...] = field(default_factory=tuple)

    @property
    def gross_notional_usd(self) -> float:
        return sum(abs(position.notional_usd) for position in self.positions)

    def notional_for_symbol(self, symbol: str) -> float:
        return sum(position.notional_usd for position in self.positions if position.symbol == symbol)

    def gross_leverage(self, account: AccountSnapshot) -> float:
        return self.gross_notional_usd / account.equity

    def gross_leverage_after(
        self,
        *,
        account: AccountSnapshot,
        symbol: str,
        target_abs_notional_usd: float,
    ) -> float:
        current_symbol_notional = abs(self.notional_for_symbol(symbol))
        adjusted_gross = self.gross_notional_usd - current_symbol_notional + target_abs_notional_usd
        return adjusted_gross / account.equity


@dataclass(frozen=True)
class TradeRequest:
    symbol: str
    side: Side
    target_notional_usd: float
    reason: str

    def __post_init__(self) -> None:
        if self.target_notional_usd <= 0 or not isfinite(self.target_notional_usd):
            raise ValueError("target_notional_usd must be a positive finite number")


# The competition force-liquidates ("stop-out") when the MT-style margin level
# falls to 30%. Forced liquidation is a red-line rule => immediate elimination,
# so every internal margin floor must sit comfortably above this number.
STOP_OUT_MARGIN_LEVEL_PCT = 30.0


@dataclass(frozen=True)
class RiskLimits:
    max_gross_leverage: float = 2.0
    max_symbol_notional_pct: float = 0.25
    max_daily_loss_pct: float = 0.025
    max_drawdown_pct: float = 0.06
    checkpoint_risk_multiplier: float = 0.5
    min_margin_level_pct: float = 300.0

    # --- Optional, competition-aligned controls (all off by default so the ---
    # --- engine's historical behaviour is unchanged unless explicitly set). ---

    # Soft margin tier: if the margin level drops to/below this (but stays above
    # ``min_margin_level_pct``) the engine goes REDUCE_ONLY instead of the hard
    # FROZEN freeze, so a transient dip does not forfeit the whole round.
    reduce_only_margin_level_pct: float | None = None

    # Drawdown "brake": linearly scale new position size from 1.0 down to 0.0 as
    # account drawdown rises from ``drawdown_derisk_start_pct`` to
    # ``drawdown_derisk_full_pct``. Smooths the equity curve (helps Sharpe rank)
    # and caps MaxDD (helps Drawdown rank) before the hard REDUCE_ONLY cliff.
    drawdown_derisk_start_pct: float | None = None
    drawdown_derisk_full_pct: float | None = None

    # When False, hitting the daily-loss stop downgrades to REDUCE_ONLY rather
    # than FROZEN (existing entries can still be trimmed). Default True keeps the
    # original freeze behaviour.
    freeze_on_daily_loss: bool = True

    def __post_init__(self) -> None:
        if self.reduce_only_margin_level_pct is not None:
            if self.reduce_only_margin_level_pct <= self.min_margin_level_pct:
                raise ValueError(
                    "reduce_only_margin_level_pct must exceed min_margin_level_pct"
                )
        start, full = self.drawdown_derisk_start_pct, self.drawdown_derisk_full_pct
        if (start is None) != (full is None):
            raise ValueError("drawdown derisk thresholds must be set together")
        if start is not None and full is not None and not (0 <= start < full):
            raise ValueError("require 0 <= drawdown_derisk_start_pct < drawdown_derisk_full_pct")

    @classmethod
    def competition_safe(
        cls,
        *,
        max_gross_leverage: float = 6.0,
        max_symbol_notional_pct: float = 0.20,
    ) -> "RiskLimits":
        """Preset that targets the published scoring formula.

        Reasoning vs. the rulebook:
          * Gross leverage is kept far below the 28x risk-discipline line and the
            30x ceiling, while allowing more return than the ultra-conservative
            2x default (Return is 70% of the score).
          * Margin floors sit far above the 30% stop-out (forced liquidation =
            elimination), with a REDUCE_ONLY tier before the hard freeze.
          * A drawdown brake protects Drawdown rank (15%) and smooths the
            15-minute equity curve that drives the Sharpe rank (10%).
        """
        return cls(
            max_gross_leverage=max_gross_leverage,
            max_symbol_notional_pct=max_symbol_notional_pct,
            max_daily_loss_pct=0.05,
            max_drawdown_pct=0.12,
            checkpoint_risk_multiplier=0.5,
            min_margin_level_pct=150.0,
            reduce_only_margin_level_pct=250.0,
            drawdown_derisk_start_pct=0.04,
            drawdown_derisk_full_pct=0.10,
            freeze_on_daily_loss=True,
        )


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    adjusted_notional_usd: float
    state: RiskState


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self.state = RiskState.NORMAL

    def evaluate(
        self,
        *,
        account: AccountSnapshot,
        portfolio: PortfolioSnapshot,
        request: TradeRequest,
        mode: CompetitionMode,
    ) -> RiskDecision:
        if self.state == RiskState.FROZEN:
            return self._block("risk engine is frozen")

        if account.margin_level_pct is not None:
            if account.margin_level_pct <= self.limits.min_margin_level_pct:
                self.state = RiskState.FROZEN
                return self._block("margin level below internal safety limit")
            if (
                self.limits.reduce_only_margin_level_pct is not None
                and account.margin_level_pct <= self.limits.reduce_only_margin_level_pct
            ):
                self.state = RiskState.REDUCE_ONLY
                return self._block("margin level in reduce-only band")

        if account.daily_pnl_pct <= -self.limits.max_daily_loss_pct:
            if self.limits.freeze_on_daily_loss:
                self.state = RiskState.FROZEN
            else:
                self.state = RiskState.REDUCE_ONLY
            return self._block("daily loss stop reached")

        if account.drawdown_pct >= self.limits.max_drawdown_pct:
            self.state = RiskState.REDUCE_ONLY
            return self._block("drawdown throttle reached")

        adjusted_notional = self._cap_symbol_notional(account, request.target_notional_usd)

        if mode == CompetitionMode.CHECKPOINT_PROTECT and account.total_pnl_pct > 0:
            adjusted_notional *= self.limits.checkpoint_risk_multiplier

        adjusted_notional *= self._drawdown_brake(account.drawdown_pct)

        leverage_after = portfolio.gross_leverage_after(
            account=account,
            symbol=request.symbol,
            target_abs_notional_usd=adjusted_notional,
        )

        if leverage_after > self.limits.max_gross_leverage:
            return self._block(
                f"gross leverage would be {leverage_after:.2f}x, "
                f"above {self.limits.max_gross_leverage:.2f}x limit"
            )

        return RiskDecision(
            approved=True,
            reason="approved",
            adjusted_notional_usd=adjusted_notional,
            state=self.state,
        )

    def _cap_symbol_notional(self, account: AccountSnapshot, requested: float) -> float:
        max_symbol_notional = account.equity * self.limits.max_symbol_notional_pct
        return min(requested, max_symbol_notional)

    def _drawdown_brake(self, drawdown_pct: float) -> float:
        """Linear scale in [0, 1]: 1.0 below the start threshold, 0.0 at/above full."""
        start = self.limits.drawdown_derisk_start_pct
        full = self.limits.drawdown_derisk_full_pct
        if start is None or full is None or drawdown_pct <= start:
            return 1.0
        if drawdown_pct >= full:
            return 0.0
        return (full - drawdown_pct) / (full - start)

    def _block(self, reason: str) -> RiskDecision:
        return RiskDecision(
            approved=False,
            reason=reason,
            adjusted_notional_usd=0.0,
            state=self.state,
        )

