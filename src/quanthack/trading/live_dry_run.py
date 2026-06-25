from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite
from pathlib import Path
from time import sleep

from quanthack.backtesting.portfolio_allocator import (
    AllocationPolicy,
    PortfolioAllocation,
    PortfolioAllocator,
    SymbolIntent,
)
from quanthack.core.clock import CompetitionClock, UTC
from quanthack.core.config import AppConfig
from quanthack.core.instruments import instrument_for
from quanthack.market.adapters import AccountAdapter, MarketDataAdapter
from quanthack.market.market_data import PriceBar, QuoteSnapshot
from quanthack.market.market_quality import MarketQualityChecker, MarketQualityLimits
from quanthack.strategies.strategy import (
    EPSILON_NOTIONAL,
    Strategy,
    normalize_strategy_name,
)
from quanthack.trading.competition_monitor import (
    CompetitionMonitor,
    CompetitionMonitorReport,
)
from quanthack.trading.execution import DryRunExecutor, ExecutionRecord, read_journal
from quanthack.trading.risk import (
    AccountSnapshot,
    PortfolioSnapshot,
    Position,
    RiskDecision,
    RiskEngine,
    RiskLimits,
    RiskState,
    Side,
    TradeRequest,
)


@dataclass(frozen=True)
class LiveDryRunSettings:
    symbols: tuple[str, ...]
    strategy_name: str
    strategy_by_symbol: tuple[tuple[str, str], ...] = ()
    timeframe: str = "M1"
    bars: int = 120
    iterations: int = 1
    poll_seconds: float = 0.0
    journal_path: str = "outputs/live_dry_run_journal.jsonl"
    monitor_csv: str = "outputs/live_competition_monitor.csv"

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("live dry-run needs at least one symbol")
        canonical_symbols: list[str] = []
        seen: set[str] = set()
        for raw_symbol in self.symbols:
            symbol = instrument_for(raw_symbol).symbol
            if symbol in seen:
                continue
            canonical_symbols.append(symbol)
            seen.add(symbol)
        object.__setattr__(self, "symbols", tuple(canonical_symbols))
        object.__setattr__(
            self,
            "strategy_name",
            normalize_strategy_name(self.strategy_name),
        )
        strategy_overrides: list[tuple[str, str]] = []
        seen_override_symbols: set[str] = set()
        for raw_symbol, raw_strategy in self.strategy_by_symbol:
            symbol = instrument_for(raw_symbol).symbol
            if symbol not in self.symbols:
                raise ValueError(
                    f"strategy override symbol {symbol} is not in live dry-run symbols"
                )
            strategy = normalize_strategy_name(raw_strategy)
            if symbol in seen_override_symbols:
                strategy_overrides = [
                    item for item in strategy_overrides if item[0] != symbol
                ]
            strategy_overrides.append((symbol, strategy))
            seen_override_symbols.add(symbol)
        object.__setattr__(
            self,
            "strategy_by_symbol",
            tuple(sorted(strategy_overrides)),
        )
        if self.bars < 2:
            raise ValueError("live dry-run bars must be at least 2")
        if self.iterations < 1:
            raise ValueError("live dry-run iterations must be at least 1")
        if self.poll_seconds < 0:
            raise ValueError("live dry-run poll_seconds cannot be negative")

    def strategy_for_symbol(self, symbol: str) -> str:
        canonical = instrument_for(symbol).symbol
        for override_symbol, strategy_name in self.strategy_by_symbol:
            if override_symbol == canonical:
                return strategy_name
        return self.strategy_name


@dataclass(frozen=True)
class LiveRiskThrottle:
    """Live-only brake that can block fresh risk without blocking exits."""

    max_active_positions: int | None = None
    reduce_only_daily_loss_pct: float | None = None
    reduce_only_rolling_sharpe: float | None = None
    metrics_csv: str = "outputs/live_metrics.csv"
    sentiment_snapshot_path: str | None = None
    sentiment_conflict_threshold: float | None = None
    symbol_state_snapshot_path: str | None = None
    blocked_symbol_states: tuple[str, ...] = ("cooldown_realized_drag",)
    small_only_symbol_states: tuple[str, ...] = ()
    small_only_max_notional_usd: float | None = None

    def __post_init__(self) -> None:
        if self.max_active_positions is not None and self.max_active_positions < 0:
            raise ValueError("max_active_positions cannot be negative")
        if self.reduce_only_daily_loss_pct is not None:
            if (
                self.reduce_only_daily_loss_pct <= 0
                or not isfinite(self.reduce_only_daily_loss_pct)
            ):
                raise ValueError("reduce_only_daily_loss_pct must be positive")
        if self.reduce_only_rolling_sharpe is not None and not isfinite(
            self.reduce_only_rolling_sharpe
        ):
            raise ValueError("reduce_only_rolling_sharpe must be finite")
        if self.sentiment_conflict_threshold is not None:
            if (
                self.sentiment_conflict_threshold <= 0
                or not isfinite(self.sentiment_conflict_threshold)
            ):
                raise ValueError("sentiment_conflict_threshold must be positive")
        if any(not state for state in self.blocked_symbol_states):
            raise ValueError("blocked_symbol_states cannot contain empty values")
        if any(not state for state in self.small_only_symbol_states):
            raise ValueError("small_only_symbol_states cannot contain empty values")
        if self.small_only_symbol_states:
            if (
                self.small_only_max_notional_usd is None
                or self.small_only_max_notional_usd <= 0
                or not isfinite(self.small_only_max_notional_usd)
            ):
                raise ValueError(
                    "small_only_max_notional_usd must be positive when "
                    "small_only_symbol_states are configured"
                )


@dataclass(frozen=True)
class LiveDryRunIteration:
    timestamp: datetime
    account: AccountSnapshot
    portfolio_before: PortfolioSnapshot
    allocation: PortfolioAllocation
    records: tuple[ExecutionRecord, ...]


@dataclass(frozen=True)
class LiveDryRunError:
    """A single iteration that failed during a resilient live run."""
    iteration_index: int
    message: str


class LiveDryRunNoSuccessfulIterationsError(RuntimeError):
    """Raised when a resilient loop never records a usable iteration."""


@dataclass(frozen=True)
class LiveDryRunResult:
    iterations: tuple[LiveDryRunIteration, ...]
    monitor_report: CompetitionMonitorReport
    # Iterations that raised but were skipped so the multi-day loop keeps running.
    errors: tuple[LiveDryRunError, ...] = ()

    @property
    def records(self) -> tuple[ExecutionRecord, ...]:
        return tuple(record for item in self.iterations for record in item.records)


class LiveDryRunEngine:
    def __init__(
        self,
        *,
        config: AppConfig,
        settings: LiveDryRunSettings,
        market_data: MarketDataAdapter,
        account_adapter: AccountAdapter,
        risk_limits: RiskLimits | None = None,
        quality_limits: MarketQualityLimits | None = None,
        allocation_policy: AllocationPolicy | None = None,
        executor: DryRunExecutor | None = None,
        live_risk_throttle: LiveRiskThrottle | None = None,
        clock: CompetitionClock | None = None,
        continue_on_error: bool = True,
        validate_quote_age_against_wall_clock: bool = False,
    ) -> None:
        self.config = config
        self.settings = settings
        # In a multi-day live deployment a single transient tick failure (bad
        # quote, network blip, missing symbol) must NOT kill the loop — a dead
        # bot risks the >8h inactivity elimination. When True, run() records the
        # error and continues to the next poll.
        self.continue_on_error = continue_on_error
        self.validate_quote_age_against_wall_clock = validate_quote_age_against_wall_clock
        self.market_data = market_data
        self.account_adapter = account_adapter
        self.risk_engine = RiskEngine(risk_limits or config.risk)
        self.quality_limits = quality_limits or config.market_quality
        if (
            validate_quote_age_against_wall_clock
            and self.quality_limits.max_future_quote_skew_seconds <= 0
        ):
            self.quality_limits = replace(
                self.quality_limits,
                max_future_quote_skew_seconds=7_200.0,
            )
        self.allocator = PortfolioAllocator(
            allocation_policy
            or AllocationPolicy(
                max_gross_leverage=(risk_limits or config.risk).max_gross_leverage,
                max_symbol_gross_pct=(risk_limits or config.risk).max_symbol_notional_pct,
            )
        )
        self.executor = executor or DryRunExecutor(Path(settings.journal_path))
        self.live_risk_throttle = live_risk_throttle
        self.clock = clock or config.competition.to_clock()
        self.monitor = CompetitionMonitor()
        self._strategies = {
            symbol: config.build_strategy(
                settings.strategy_for_symbol(symbol),
                symbol=symbol,
            )
            for symbol in settings.symbols
        }
        self._holding_periods = self._initial_holding_periods()
        self._peak_equity = config.competition.starting_equity
        self._day_start_equity = config.competition.starting_equity
        self.reconnects = 0

    def run(
        self,
        progress_callback: Callable[
            [int, LiveDryRunIteration | None, LiveDryRunError | None],
            None,
        ]
        | None = None,
    ) -> LiveDryRunResult:
        iterations: list[LiveDryRunIteration] = []
        errors: list[LiveDryRunError] = []
        for index in range(self.settings.iterations):
            try:
                iteration = self.run_once()
                iterations.append(iteration)
                if progress_callback is not None:
                    progress_callback(index, iteration, None)
            except Exception as exc:  # noqa: BLE001 - keep the multi-day loop alive
                if not self.continue_on_error:
                    raise
                error = LiveDryRunError(iteration_index=index, message=repr(exc))
                errors.append(error)
                if progress_callback is not None:
                    progress_callback(index, None, error)
                # A dropped MT5 connection makes every tick fail; best-effort
                # reconnect so the bot recovers instead of idling into the >8h
                # inactivity elimination.
                self._attempt_reconnect()
            if index < self.settings.iterations - 1 and self.settings.poll_seconds > 0:
                sleep(self.settings.poll_seconds)
        if not iterations:
            detail = "; ".join(
                f"iteration {error.iteration_index}: {error.message}" for error in errors[-3:]
            )
            suffix = f": {detail}" if detail else ""
            raise LiveDryRunNoSuccessfulIterationsError(
                f"live dry-run produced no successful iterations{suffix}"
            )
        return LiveDryRunResult(
            iterations=tuple(iterations),
            monitor_report=self.monitor.report(),
            errors=tuple(errors),
        )

    def _attempt_reconnect(self) -> bool:
        """Best-effort MT5 reconnect after a failed tick. Returns True on success.

        No-op for adapters without connect() (e.g. the CSV/backtest adapter), so
        it is safe in tests and dry-runs.
        """
        connect = getattr(self.market_data, "connect", None)
        if not callable(connect):
            return False
        close = getattr(self.market_data, "close", None)
        try:
            if callable(close):
                close()
            connect()
            self.reconnects += 1
            return True
        except Exception:  # noqa: BLE001 - reconnection is best-effort
            return False

    def run_once(self) -> LiveDryRunIteration:
        histories = {
            symbol: self.market_data.get_recent_bars(
                symbol,
                timeframe=self.settings.timeframe,
                count=self.settings.bars,
            )
            for symbol in self.settings.symbols
        }
        # Quotes are the freshest data in the decision; fetch them after slower
        # history reads so live wall-clock age checks do not penalize collection time.
        quotes = {
            symbol: self.market_data.get_latest_quote(symbol)
            for symbol in self.settings.symbols
        }
        self._update_strategy_context(histories=histories, quotes=quotes)
        timestamp = _iteration_timestamp(
            quotes,
            validate_quote_age_against_wall_clock=(
                self.validate_quote_age_against_wall_clock
            ),
        )
        account = self.account_adapter.get_account_snapshot(
            starting_equity=self.config.competition.starting_equity,
            day_start_equity=self._day_start_equity,
            peak_equity=self._peak_equity,
        )
        self._peak_equity = max(self._peak_equity, account.equity)
        portfolio_before = self.executor.current_portfolio()
        raw_intents = tuple(
            self._build_intent(
                symbol=symbol,
                strategy=self._strategies[symbol],
                quote=quotes[symbol],
                bars=histories[symbol],
                portfolio=portfolio_before,
            )
            for symbol in self.settings.symbols
        )
        intents = self._apply_live_risk_throttle(
            raw_intents,
            account=account,
            portfolio=portfolio_before,
        )
        allocation = self.allocator.allocate(
            intents,
            equity=account.equity,
            timestamp=timestamp.isoformat(timespec="seconds"),
        )
        records = self._submit_allocation(
            allocation=allocation,
            account=account,
            portfolio_before=portfolio_before,
            timestamp=timestamp,
        )
        portfolio_after = self.executor.current_portfolio()
        self._update_holding_periods(
            before=portfolio_before,
            after=portfolio_after,
            records=records,
        )
        self.monitor.record(
            timestamp=timestamp,
            account=account,
            portfolio=portfolio_after,
            accepted_trade_count=_accepted_count(self.executor.journal_path),
        )
        return LiveDryRunIteration(
            timestamp=timestamp,
            account=account,
            portfolio_before=portfolio_before,
            allocation=allocation,
            records=records,
        )

    def _build_intent(
        self,
        *,
        symbol: str,
        strategy: Strategy,
        quote: QuoteSnapshot,
        bars: tuple[PriceBar, ...],
        portfolio: PortfolioSnapshot,
    ) -> SymbolIntent:
        canonical = instrument_for(symbol).symbol
        current_notional = portfolio.notional_for_symbol(canonical)
        quality = MarketQualityChecker(self.quality_limits).evaluate(
            quote=quote,
            as_of=(
                datetime.now(tz=UTC)
                if self.validate_quote_age_against_wall_clock
                else quote.timestamp
            ),
        )
        if not quality.ok:
            return SymbolIntent(
                symbol=canonical,
                target_notional_usd=current_notional,
                current_notional_usd=current_notional,
                reason=f"market quality hold: {quality.reason}",
                primary_signal="market_quality",
            )
        closes = [bar.close for bar in bars]
        if hasattr(strategy, "generate_decision"):
            decision = strategy.generate_decision(
                closes,
                current_notional_usd=current_notional,
                holding_period=self._holding_periods[canonical],
                quote=quote,
            )
            target = decision.target_notional_usd if decision.is_trade_intent else current_notional
            return SymbolIntent(
                symbol=canonical,
                target_notional_usd=target,
                current_notional_usd=current_notional,
                reason=decision.reason,
                primary_signal=decision.primary_signal,
                supporting_signals=decision.supporting_signals,
                conflicting_signals=decision.conflicting_signals,
            )

        request = strategy.generate_request(closes)
        if request is None:
            return SymbolIntent(
                symbol=canonical,
                target_notional_usd=current_notional,
                current_notional_usd=current_notional,
                reason="no strategy request",
            )
        target = request.target_notional_usd if request.side == Side.BUY else -request.target_notional_usd
        return SymbolIntent(
            symbol=canonical,
            target_notional_usd=target,
            current_notional_usd=current_notional,
            reason=request.reason,
            primary_signal="request",
        )

    def _apply_live_risk_throttle(
        self,
        intents: tuple[SymbolIntent, ...],
        *,
        account: AccountSnapshot,
        portfolio: PortfolioSnapshot,
    ) -> tuple[SymbolIntent, ...]:
        throttle = self.live_risk_throttle
        if throttle is None:
            return intents

        reduce_only_reasons = self._live_reduce_only_reasons(account)
        sentiment_scores = _read_live_sentiment_scores(
            Path(throttle.sentiment_snapshot_path)
            if throttle.sentiment_snapshot_path
            else None
        )
        symbol_states = _read_live_symbol_states(
            Path(throttle.symbol_state_snapshot_path)
            if throttle.symbol_state_snapshot_path
            else None
        )
        active_symbols = {
            position.symbol
            for position in portfolio.positions
            if abs(position.notional_usd) > EPSILON_NOTIONAL
        }
        adjusted: list[SymbolIntent] = []
        for intent in intents:
            target = intent.target_notional_usd
            reasons: list[str] = []
            if reduce_only_reasons:
                reduced_target = _reduce_only_target(
                    target=target,
                    current=intent.current_notional_usd,
                )
                if abs(reduced_target - target) > EPSILON_NOTIONAL:
                    target = reduced_target
                    reasons.extend(reduce_only_reasons)
            sentiment_reason = _sentiment_conflict_reason(
                symbol=intent.symbol,
                target=target,
                current=intent.current_notional_usd,
                scores=sentiment_scores,
                threshold=throttle.sentiment_conflict_threshold,
            )
            if sentiment_reason is not None:
                reduced_target = _reduce_only_target(
                    target=target,
                    current=intent.current_notional_usd,
                )
                if abs(reduced_target - target) > EPSILON_NOTIONAL:
                    target = reduced_target
                    reasons.append(sentiment_reason)
            symbol_state_reason = _symbol_state_block_reason(
                symbol=intent.symbol,
                target=target,
                current=intent.current_notional_usd,
                states=symbol_states,
                blocked_states=throttle.blocked_symbol_states,
            )
            if symbol_state_reason is not None:
                reduced_target = _reduce_only_target(
                    target=target,
                    current=intent.current_notional_usd,
                )
                if abs(reduced_target - target) > EPSILON_NOTIONAL:
                    target = reduced_target
                    reasons.append(symbol_state_reason)
            small_only_reason = _symbol_state_small_only_reason(
                symbol=intent.symbol,
                target=target,
                current=intent.current_notional_usd,
                states=symbol_states,
                small_only_states=throttle.small_only_symbol_states,
                max_notional_usd=throttle.small_only_max_notional_usd,
            )
            if small_only_reason is not None:
                capped_target = _small_only_target(
                    target=target,
                    current=intent.current_notional_usd,
                    max_notional_usd=throttle.small_only_max_notional_usd,
                )
                if abs(capped_target - target) > EPSILON_NOTIONAL:
                    target = capped_target
                    reasons.append(small_only_reason)
            if (
                throttle.max_active_positions is not None
                and _would_create_new_active_symbol(
                    symbol=intent.symbol,
                    target=target,
                    active_symbols=active_symbols,
                )
            ):
                if len(active_symbols) >= throttle.max_active_positions:
                    target = 0.0
                    reasons.append(
                        "active position cap "
                        f"{len(active_symbols)}/{throttle.max_active_positions}"
                    )
                else:
                    active_symbols.add(intent.symbol)
            if reasons:
                adjusted.append(
                    SymbolIntent(
                        symbol=intent.symbol,
                        target_notional_usd=target,
                        current_notional_usd=intent.current_notional_usd,
                        reason=_append_live_throttle_reason(intent.reason, reasons),
                        primary_signal=intent.primary_signal,
                        supporting_signals=intent.supporting_signals,
                        conflicting_signals=intent.conflicting_signals,
                    )
                )
            else:
                adjusted.append(intent)
        return tuple(adjusted)

    def _live_reduce_only_reasons(self, account: AccountSnapshot) -> tuple[str, ...]:
        throttle = self.live_risk_throttle
        if throttle is None:
            return ()
        reasons: list[str] = []
        if (
            throttle.reduce_only_daily_loss_pct is not None
            and account.daily_pnl_pct <= -throttle.reduce_only_daily_loss_pct
        ):
            reasons.append(
                "daily P/L "
                f"{account.daily_pnl_pct:.3%} below live new-risk stop "
                f"-{throttle.reduce_only_daily_loss_pct:.3%}"
            )
        if throttle.reduce_only_rolling_sharpe is not None:
            rolling_sharpe = _latest_metric(
                Path(throttle.metrics_csv),
                "rolling_sharpe_15",
            )
            if (
                rolling_sharpe is not None
                and rolling_sharpe <= throttle.reduce_only_rolling_sharpe
            ):
                reasons.append(
                    "rolling Sharpe "
                    f"{rolling_sharpe:.2f} below live new-risk stop "
                    f"{throttle.reduce_only_rolling_sharpe:.2f}"
                )
        return tuple(reasons)

    def _update_strategy_context(
        self,
        *,
        histories: dict[str, tuple[PriceBar, ...]],
        quotes: dict[str, QuoteSnapshot],
    ) -> None:
        closes_by_symbol = {
            symbol: tuple(bar.close for bar in bars)
            for symbol, bars in histories.items()
        }
        for strategy in self._strategies.values():
            update_context = getattr(strategy, "update_portfolio_context", None)
            if callable(update_context):
                update_context(
                    closes_by_symbol=closes_by_symbol,
                    quotes_by_symbol=quotes,
                )

    def _submit_allocation(
        self,
        *,
        allocation: PortfolioAllocation,
        account: AccountSnapshot,
        portfolio_before: PortfolioSnapshot,
        timestamp: datetime,
    ) -> tuple[ExecutionRecord, ...]:
        records: list[ExecutionRecord] = []
        mode = self.clock.mode_at(timestamp)
        portfolio = portfolio_before
        for target in allocation.targets:
            if abs(target.change_notional_usd) <= EPSILON_NOTIONAL:
                continue
            request, decision = self._request_and_decision(
                target_symbol=target.symbol,
                current_notional=target.current_notional_usd,
                adjusted_target=target.adjusted_notional_usd,
                account=account,
                portfolio=portfolio,
                mode=mode,
                reason=_allocation_reason(target),
            )
            record = self.executor.submit(
                account=account,
                request=request,
                decision=decision,
                mode=mode,
                portfolio_before=portfolio,
            )
            records.append(record)
            if decision.approved:
                portfolio = _portfolio_after_target(
                    portfolio=portfolio,
                    symbol=target.symbol,
                    signed_notional=(
                        _signed_target(target.adjusted_notional_usd, decision.adjusted_notional_usd)
                    ),
                )
        return tuple(records)

    def _request_and_decision(
        self,
        *,
        target_symbol: str,
        current_notional: float,
        adjusted_target: float,
        account: AccountSnapshot,
        portfolio: PortfolioSnapshot,
        mode,
        reason: str,
    ) -> tuple[TradeRequest, RiskDecision]:
        if abs(adjusted_target) <= EPSILON_NOTIONAL:
            side = Side.SELL if current_notional > 0 else Side.BUY
            request = TradeRequest(
                symbol=target_symbol,
                side=side,
                target_notional_usd=max(abs(current_notional), 1.0),
                reason=f"{reason}; allocated exit",
            )
            return (
                request,
                RiskDecision(
                    approved=True,
                    reason="allocated exit",
                    adjusted_notional_usd=0.0,
                    state=self.risk_engine.state,
                ),
            )

        side = Side.BUY if adjusted_target > 0 else Side.SELL
        request = TradeRequest(
            symbol=target_symbol,
            side=side,
            target_notional_usd=abs(adjusted_target),
            reason=reason,
        )
        decision = self.risk_engine.evaluate(
            account=account,
            portfolio=portfolio,
            request=request,
            mode=mode,
        )
        return request, decision

    def _update_holding_periods(
        self,
        *,
        before: PortfolioSnapshot,
        after: PortfolioSnapshot,
        records: tuple[ExecutionRecord, ...],
    ) -> None:
        traded_symbols = {record.request.symbol for record in records if record.decision.approved}
        for symbol in self.settings.symbols:
            previous_direction = _notional_direction(before.notional_for_symbol(symbol))
            current_direction = _notional_direction(after.notional_for_symbol(symbol))
            if current_direction == 0:
                self._holding_periods[symbol] = 0
            elif symbol in traded_symbols and current_direction != previous_direction:
                self._holding_periods[symbol] = 1
            else:
                self._holding_periods[symbol] += 1

    def _initial_holding_periods(self) -> dict[str, int]:
        holding = {symbol: 0 for symbol in self.settings.symbols}
        try:
            portfolio = self.executor.current_portfolio()
        except Exception:  # noqa: BLE001 - startup state recovery is best effort
            return holding

        active_directions = {
            symbol: _notional_direction(portfolio.notional_for_symbol(symbol))
            for symbol in self.settings.symbols
            if _notional_direction(portfolio.notional_for_symbol(symbol)) != 0
        }
        if not active_directions:
            return holding

        opened_at = _latest_open_times_by_symbol(
            Path(self.executor.journal_path),
            active_directions,
        )
        seconds_per_bar = _timeframe_seconds(self.settings.timeframe)
        now = datetime.now(tz=UTC)
        for symbol in active_directions:
            opened = opened_at.get(symbol)
            if opened is None:
                holding[symbol] = 1
                continue
            elapsed_seconds = max(0.0, (now - opened).total_seconds())
            holding[symbol] = max(1, int(elapsed_seconds // seconds_per_bar))
        return holding


def _allocation_reason(target) -> str:
    parts = []
    if target.intent_reason:
        parts.append(target.intent_reason)
    if target.reasons:
        parts.append(f"allocation: {'; '.join(target.reasons)}")
    return "; ".join(parts) if parts else "allocated target"


def _iteration_timestamp(
    quotes: dict[str, QuoteSnapshot],
    *,
    validate_quote_age_against_wall_clock: bool,
    now: datetime | None = None,
) -> datetime:
    if validate_quote_age_against_wall_clock:
        current = now or datetime.now(tz=UTC)
        if current.tzinfo is None:
            raise ValueError("live iteration timestamp requires timezone-aware wall time")
        return current.astimezone(UTC)
    return max(quote.timestamp for quote in quotes.values())


def _accepted_count(journal_path: Path) -> int:
    return len(
        [
            record
            for record in read_journal(journal_path)
            if record.get("status") == "DRY_RUN_ACCEPTED"
        ]
    )


def _latest_open_times_by_symbol(
    journal_path: Path,
    active_directions: dict[str, int],
) -> dict[str, datetime]:
    opened_at: dict[str, datetime] = {}
    blocked_symbols: set[str] = set()
    for record in reversed(read_journal(journal_path)):
        symbol = str((record.get("request") or {}).get("symbol") or "")
        if (
            symbol not in active_directions
            or symbol in opened_at
            or symbol in blocked_symbols
        ):
            continue
        direction = _journal_record_direction(record)
        if direction is None:
            continue
        if direction == active_directions[symbol]:
            opened = _parse_journal_datetime(record.get("created_at_utc"))
            if opened is not None:
                opened_at[symbol] = opened
        else:
            blocked_symbols.add(symbol)
        if len(opened_at) + len(blocked_symbols) == len(active_directions):
            break
    return opened_at


def _journal_record_direction(record: dict) -> int | None:
    if record.get("status") not in {"DRY_RUN_ACCEPTED", "MT5_FILLED"}:
        return None
    decision = record.get("decision") or {}
    if not decision.get("approved", False):
        return None
    try:
        adjusted_notional = float(decision.get("adjusted_notional_usd") or 0.0)
    except (TypeError, ValueError):
        return None
    if adjusted_notional <= EPSILON_NOTIONAL:
        return 0
    side = str((record.get("request") or {}).get("side") or "")
    if side == Side.BUY.value:
        return 1
    if side == Side.SELL.value:
        return -1
    return 0


def _parse_journal_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timeframe_seconds(timeframe: str) -> float:
    normalized = timeframe.strip().upper()
    if normalized.startswith("M"):
        return max(60.0, float(int(normalized[1:] or "1") * 60))
    if normalized.startswith("H"):
        return max(60.0, float(int(normalized[1:] or "1") * 3_600))
    if normalized.startswith("D"):
        return 86_400.0
    return 60.0


def _portfolio_after_target(
    *,
    portfolio: PortfolioSnapshot,
    symbol: str,
    signed_notional: float,
) -> PortfolioSnapshot:
    positions = {
        position.symbol: position.notional_usd
        for position in portfolio.positions
    }
    if abs(signed_notional) <= EPSILON_NOTIONAL:
        positions.pop(symbol, None)
    else:
        positions[symbol] = signed_notional
    return PortfolioSnapshot(
        positions=tuple(
            sorted(
                (
                    Position(symbol=position_symbol, notional_usd=notional)
                    for position_symbol, notional in positions.items()
                    if abs(notional) > EPSILON_NOTIONAL
                ),
                key=lambda item: item.symbol,
            )
        )
    )


def _signed_target(requested_signed: float, adjusted_abs: float) -> float:
    if abs(adjusted_abs) <= EPSILON_NOTIONAL:
        return 0.0
    return adjusted_abs if requested_signed > 0 else -adjusted_abs


def _notional_direction(notional: float) -> int:
    if notional > EPSILON_NOTIONAL:
        return 1
    if notional < -EPSILON_NOTIONAL:
        return -1
    return 0


def _active_position_count(portfolio: PortfolioSnapshot) -> int:
    return len(
        [
            position
            for position in portfolio.positions
            if abs(position.notional_usd) > EPSILON_NOTIONAL
        ]
    )


def _would_create_new_active_symbol(
    *,
    symbol: str,
    target: float,
    active_symbols: set[str],
) -> bool:
    return symbol not in active_symbols and abs(target) > EPSILON_NOTIONAL


def _is_expanding_position(*, target: float, current: float) -> bool:
    target_direction = _notional_direction(target)
    current_direction = _notional_direction(current)
    if target_direction == 0:
        return False
    if current_direction == 0:
        return True
    if target_direction != current_direction:
        return True
    return abs(target) > abs(current) + EPSILON_NOTIONAL


def _reduce_only_target(*, target: float, current: float) -> float:
    target_direction = _notional_direction(target)
    current_direction = _notional_direction(current)
    if current_direction == 0:
        return 0.0
    if target_direction == 0:
        return 0.0
    if target_direction != current_direction:
        return 0.0
    if abs(target) >= abs(current):
        return current
    return target


def _sentiment_conflict_reason(
    *,
    symbol: str,
    target: float,
    current: float,
    scores: dict[str, float],
    threshold: float | None,
) -> str | None:
    if threshold is None or not _is_expanding_position(target=target, current=current):
        return None
    target_direction = _notional_direction(target)
    sentiment_score = scores.get(symbol)
    if sentiment_score is None:
        return None
    if target_direction * sentiment_score >= -threshold:
        return None
    side = "long" if target_direction > 0 else "short"
    return (
        f"headline sentiment conflict {sentiment_score:.2f} against "
        f"{side} {symbol} entry"
    )


def _symbol_state_block_reason(
    *,
    symbol: str,
    target: float,
    current: float,
    states: dict[str, str],
    blocked_states: tuple[str, ...],
) -> str | None:
    if not blocked_states or not _is_expanding_position(target=target, current=current):
        return None
    state = states.get(symbol)
    if state not in blocked_states:
        return None
    return f"live attribution state {state} blocks fresh {symbol} risk"


def _symbol_state_small_only_reason(
    *,
    symbol: str,
    target: float,
    current: float,
    states: dict[str, str],
    small_only_states: tuple[str, ...],
    max_notional_usd: float | None,
) -> str | None:
    if (
        not small_only_states
        or max_notional_usd is None
        or not _is_expanding_position(target=target, current=current)
    ):
        return None
    state = states.get(symbol)
    if state not in small_only_states:
        return None
    return (
        f"live attribution state {state} caps fresh {symbol} risk "
        f"at {max_notional_usd:.0f} notional"
    )


def _small_only_target(
    *,
    target: float,
    current: float,
    max_notional_usd: float | None,
) -> float:
    if max_notional_usd is None or not _is_expanding_position(
        target=target,
        current=current,
    ):
        return target
    target_direction = _notional_direction(target)
    current_direction = _notional_direction(current)
    if target_direction == 0:
        return 0.0
    if current_direction != 0 and target_direction != current_direction:
        return 0.0
    if current_direction == target_direction and abs(current) >= max_notional_usd:
        return current
    return target_direction * min(abs(target), max_notional_usd)


def _append_live_throttle_reason(reason: str, throttle_reasons: list[str]) -> str:
    joined = "; ".join(throttle_reasons)
    if not reason:
        return f"live throttle: {joined}"
    return f"{reason}; live throttle: {joined}"


def _latest_metric(path: Path, field: str) -> float | None:
    if not path.exists():
        return None
    last_value: float | None = None
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_value = row.get(field)
                if raw_value in (None, ""):
                    continue
                last_value = float(raw_value)
    except (OSError, ValueError):
        return None
    return last_value


def _read_live_sentiment_scores(path: Path | None) -> dict[str, float]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    pairs = data.get("pairs") if isinstance(data, dict) else None
    if not isinstance(pairs, dict):
        return {}
    scores: dict[str, float] = {}
    for raw_symbol, item in pairs.items():
        if not isinstance(item, dict):
            continue
        try:
            scores[instrument_for(str(raw_symbol)).symbol] = float(item.get("score"))
        except (KeyError, TypeError, ValueError):
            continue
    return scores


def _read_live_symbol_states(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    symbols = data.get("symbols") if isinstance(data, dict) else None
    if not isinstance(symbols, dict):
        return {}
    states: dict[str, str] = {}
    for raw_symbol, item in symbols.items():
        if not isinstance(item, dict):
            continue
        state = item.get("state")
        if not isinstance(state, str):
            continue
        try:
            states[instrument_for(str(raw_symbol)).symbol] = state
        except KeyError:
            continue
    return states
