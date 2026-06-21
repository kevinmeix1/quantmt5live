from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.core.clock import UTC
from quanthack.core.config import load_config
from quanthack.market.market_data import PriceBar, QuoteSnapshot
from quanthack.trading.execution import DryRunExecutor, read_journal
from quanthack.trading.live_dry_run import LiveDryRunEngine, LiveDryRunSettings
from quanthack.trading.risk import AccountSnapshot


class LiveDryRunTest(TestCase):
    def test_live_dry_run_builds_allocated_dry_run_records(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("eurusd", "USDJPY"),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_BalancedMomentumMarket(),
                account_adapter=_StaticAccount(),
                executor=DryRunExecutor(journal),
            )

            result = engine.run()
            saved_records = read_journal(journal)

        self.assertEqual(settings.symbols, ("EURUSD", "USDJPY"))
        self.assertEqual(len(result.iterations), 1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(len(saved_records), 2)
        self.assertTrue(all(record.status == "DRY_RUN_ACCEPTED" for record in result.records))
        self.assertEqual(result.monitor_report.latest.accepted_trade_count, 2)
        self.assertGreater(result.monitor_report.latest.gross_notional_usd, 0)
        self.assertLess(result.monitor_report.latest.net_directional_exposure, 0.80)

    def test_live_dry_run_settings_validate_loop_controls(self) -> None:
        with self.assertRaisesRegex(ValueError, "bars"):
            LiveDryRunSettings(symbols=("EURUSD",), strategy_name="simple_momentum", bars=1)
        with self.assertRaisesRegex(ValueError, "iterations"):
            LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                iterations=0,
            )

    def test_live_dry_run_settings_validate_strategy_map_symbols(self) -> None:
        with self.assertRaisesRegex(ValueError, "override symbol"):
            LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                strategy_by_symbol=(("USDJPY", "macd_momentum"),),
            )

    def test_live_dry_run_builds_per_symbol_strategy_overrides(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD", "USDJPY"),
                strategy_name="simple_momentum",
                strategy_by_symbol=(("USDJPY", "macd_momentum"),),
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_BalancedMomentumMarket(),
                account_adapter=_StaticAccount(),
                executor=DryRunExecutor(journal),
            )

        self.assertEqual(settings.strategy_name, "simple_momentum")
        self.assertEqual(settings.strategy_by_symbol, (("USDJPY", "macd_momentum"),))
        self.assertEqual(settings.strategy_for_symbol("EURUSD"), "simple_momentum")
        self.assertEqual(settings.strategy_for_symbol("USDJPY"), "macd_momentum")
        self.assertEqual(engine._strategies["EURUSD"].__class__.__name__, "SimpleMomentumStrategy")
        self.assertEqual(engine._strategies["USDJPY"].__class__.__name__, "MacdMomentumStrategy")


class LiveDryRunResilienceTest(TestCase):
    """A transient tick failure must not kill the multi-day loop (else >8h
    inactivity => elimination)."""

    def _engine(self, *, journal: Path, continue_on_error: bool) -> LiveDryRunEngine:
        config = load_config("configs/default.toml")
        settings = LiveDryRunSettings(
            symbols=("EURUSD",),
            strategy_name="simple_momentum",
            bars=5,
            iterations=2,
            journal_path=str(journal),
        )
        return LiveDryRunEngine(
            config=config,
            settings=settings,
            market_data=_FlakyMarket(),
            account_adapter=_StaticAccount(),
            executor=DryRunExecutor(journal),
            continue_on_error=continue_on_error,
        )

    def test_transient_failure_is_skipped_and_loop_continues(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            result = self._engine(journal=journal, continue_on_error=True).run()
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].iteration_index, 0)
        self.assertEqual(len(result.iterations), 1)  # second tick still ran

    def test_can_opt_out_of_resilience(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            engine = self._engine(journal=journal, continue_on_error=False)
            with self.assertRaises(RuntimeError):
                engine.run()

    def test_reconnect_attempted_after_failed_tick(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",), strategy_name="simple_momentum",
                bars=5, iterations=2, journal_path=str(journal),
            )
            market = _ReconnectingMarket()
            engine = LiveDryRunEngine(
                config=config, settings=settings, market_data=market,
                account_adapter=_StaticAccount(), executor=DryRunExecutor(journal),
            )
            result = engine.run()
        self.assertEqual(len(result.errors), 1)            # first tick failed
        self.assertEqual(market.connect_calls, 1)          # reconnect attempted
        self.assertEqual(engine.reconnects, 1)
        self.assertEqual(len(result.iterations), 1)         # recovered on 2nd tick


class _FlakyMarket:
    """Wraps the balanced market but raises on the first quote fetch only."""

    def __init__(self) -> None:
        self._inner = _BalancedMomentumMarket()
        self._calls = 0

    def supported_symbols(self) -> tuple[str, ...]:
        return self._inner.supported_symbols()

    def get_latest_quote(self, symbol: str) -> QuoteSnapshot:
        self._calls += 1
        if self._calls == 1:
            raise RuntimeError("transient feed error")
        return self._inner.get_latest_quote(symbol)

    def get_recent_bars(self, symbol: str, *, timeframe: str, count: int) -> tuple[PriceBar, ...]:
        return self._inner.get_recent_bars(symbol, timeframe=timeframe, count=count)


class _ReconnectingMarket(_FlakyMarket):
    """Flaky feed that also exposes connect()/close() so the loop can reconnect."""

    def __init__(self) -> None:
        super().__init__()
        self.connect_calls = 0
        self.close_calls = 0

    def connect(self) -> None:
        self.connect_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class _BalancedMomentumMarket:
    def __init__(self) -> None:
        start = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
        self._bars = {
            "EURUSD": _bars("EURUSD", (1.1000, 1.1020, 1.1040, 1.1060, 1.1080), start),
            "USDJPY": _bars("USDJPY", (155.00, 154.70, 154.40, 154.10, 153.80), start),
        }
        self._quotes = {
            "EURUSD": QuoteSnapshot(
                timestamp=start + timedelta(minutes=4),
                symbol="EURUSD",
                bid=1.10795,
                ask=1.10805,
            ),
            "USDJPY": QuoteSnapshot(
                timestamp=start + timedelta(minutes=4),
                symbol="USDJPY",
                bid=153.799,
                ask=153.801,
            ),
        }

    def supported_symbols(self) -> tuple[str, ...]:
        return ("EURUSD", "USDJPY")

    def get_latest_quote(self, symbol: str) -> QuoteSnapshot:
        return self._quotes[symbol]

    def get_recent_bars(
        self,
        symbol: str,
        *,
        timeframe: str,
        count: int,
    ) -> tuple[PriceBar, ...]:
        return self._bars[symbol][-count:]


class _StaticAccount:
    def get_account_snapshot(
        self,
        *,
        starting_equity: float,
        day_start_equity: float,
        peak_equity: float,
    ) -> AccountSnapshot:
        return AccountSnapshot(
            equity=1_000_000,
            starting_equity=starting_equity,
            day_start_equity=day_start_equity,
            peak_equity=peak_equity,
            margin_level_pct=2_000,
        )


def _bars(symbol: str, closes: tuple[float, ...], start: datetime) -> tuple[PriceBar, ...]:
    return tuple(
        PriceBar(
            timestamp=start + timedelta(minutes=index),
            symbol=symbol,
            close=close,
        )
        for index, close in enumerate(closes)
    )
