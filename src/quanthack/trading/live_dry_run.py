from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
        clock: CompetitionClock | None = None,
        continue_on_error: bool = True,
    ) -> None:
        self.config = config
        self.settings = settings
        # In a multi-day live deployment a single transient tick failure (bad
        # quote, network blip, missing symbol) must NOT kill the loop — a dead
        # bot risks the >8h inactivity elimination. When True, run() records the
        # error and continues to the next poll.
        self.continue_on_error = continue_on_error
        self.market_data = market_data
        self.account_adapter = account_adapter
        self.risk_engine = RiskEngine(risk_limits or config.risk)
        self.quality_limits = quality_limits or config.market_quality
        self.allocator = PortfolioAllocator(
            allocation_policy
            or AllocationPolicy(
                max_gross_leverage=(risk_limits or config.risk).max_gross_leverage,
                max_symbol_gross_pct=(risk_limits or config.risk).max_symbol_notional_pct,
            )
        )
        self.executor = executor or DryRunExecutor(Path(settings.journal_path))
        self.clock = clock or config.competition.to_clock()
        self.monitor = CompetitionMonitor()
        self._strategies = {
            symbol: config.build_strategy(
                settings.strategy_for_symbol(symbol),
                symbol=symbol,
            )
            for symbol in settings.symbols
        }
        self._holding_periods = {symbol: 0 for symbol in settings.symbols}
        self._peak_equity = config.competition.starting_equity
        self._day_start_equity = config.competition.starting_equity
        self.reconnects = 0

    def run(self) -> LiveDryRunResult:
        iterations: list[LiveDryRunIteration] = []
        errors: list[LiveDryRunError] = []
        for index in range(self.settings.iterations):
            try:
                iterations.append(self.run_once())
            except Exception as exc:  # noqa: BLE001 - keep the multi-day loop alive
                if not self.continue_on_error:
                    raise
                errors.append(LiveDryRunError(iteration_index=index, message=repr(exc)))
                # A dropped MT5 connection makes every tick fail; best-effort
                # reconnect so the bot recovers instead of idling into the >8h
                # inactivity elimination.
                self._attempt_reconnect()
            if index < self.settings.iterations - 1 and self.settings.poll_seconds > 0:
                sleep(self.settings.poll_seconds)
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
        quotes = {
            symbol: self.market_data.get_latest_quote(symbol)
            for symbol in self.settings.symbols
        }
        histories = {
            symbol: self.market_data.get_recent_bars(
                symbol,
                timeframe=self.settings.timeframe,
                count=self.settings.bars,
            )
            for symbol in self.settings.symbols
        }
        self._update_strategy_context(histories=histories, quotes=quotes)
        timestamp = max(quote.timestamp for quote in quotes.values())
        account = self.account_adapter.get_account_snapshot(
            starting_equity=self.config.competition.starting_equity,
            day_start_equity=self._day_start_equity,
            peak_equity=self._peak_equity,
        )
        self._peak_equity = max(self._peak_equity, account.equity)
        portfolio_before = self.executor.current_portfolio()
        intents = tuple(
            self._build_intent(
                symbol=symbol,
                strategy=self._strategies[symbol],
                quote=quotes[symbol],
                bars=histories[symbol],
                portfolio=portfolio_before,
            )
            for symbol in self.settings.symbols
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
            as_of=quote.timestamp,
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


def _allocation_reason(target) -> str:
    parts = []
    if target.intent_reason:
        parts.append(target.intent_reason)
    if target.reasons:
        parts.append(f"allocation: {'; '.join(target.reasons)}")
    return "; ".join(parts) if parts else "allocated target"


def _accepted_count(journal_path: Path) -> int:
    return len(
        [
            record
            for record in read_journal(journal_path)
            if record.get("status") == "DRY_RUN_ACCEPTED"
        ]
    )


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
