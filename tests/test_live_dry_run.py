from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.portfolio_allocator import AllocationPolicy
from quanthack.core.clock import CompetitionMode
from quanthack.core.clock import UTC
from quanthack.core.config import load_config
from quanthack.market.market_data import PriceBar, QuoteSnapshot
from quanthack.trading.execution import DryRunExecutor, read_journal
from quanthack.trading.live_dry_run import (
    LiveDryRunEngine,
    LiveDryRunNoSuccessfulIterationsError,
    LiveDryRunSettings,
    LiveRiskThrottle,
    _iteration_timestamp,
)
from quanthack.trading.risk import (
    AccountSnapshot,
    PortfolioSnapshot,
    Position,
    RiskDecision,
    RiskState,
    Side,
    TradeRequest,
)


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

    def test_live_dry_run_recovers_holding_period_from_dry_run_journal(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            opened = datetime.now(tz=UTC) - timedelta(minutes=10)
            journal.write_text(
                json.dumps(
                    {
                        "created_at_utc": opened.isoformat(timespec="seconds"),
                        "status": "DRY_RUN_ACCEPTED",
                        "request": {"symbol": "EURUSD", "side": "BUY"},
                        "decision": {
                            "approved": True,
                            "adjusted_notional_usd": 50_000,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                timeframe="M1",
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_BalancedMomentumMarket(),
                account_adapter=_StaticAccount(),
                executor=DryRunExecutor(journal),
            )

        self.assertGreaterEqual(engine._holding_periods["EURUSD"], 9)

    def test_live_dry_run_recovers_holding_period_from_mt5_journal(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            opened = datetime.now(tz=UTC) - timedelta(minutes=6)
            journal.write_text(
                json.dumps(
                    {
                        "created_at_utc": opened.isoformat(timespec="seconds"),
                        "status": "MT5_FILLED",
                        "request": {"symbol": "USDCAD", "side": "SELL"},
                        "decision": {
                            "approved": True,
                            "adjusted_notional_usd": 25_000,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("USDCAD",),
                strategy_name="opportunity_probe",
                timeframe="M1",
                journal_path=str(journal),
            )
            executor = _StaticPortfolioExecutor(
                journal=journal,
                portfolio=PortfolioSnapshot(
                    positions=(Position(symbol="USDCAD", notional_usd=-10_000),)
                ),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_BalancedMomentumMarket(),
                account_adapter=_StaticAccount(),
                executor=executor,
            )

        self.assertGreaterEqual(engine._holding_periods["USDCAD"], 5)

    def test_live_dry_run_does_not_reuse_stale_holding_after_exit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            old_open = datetime.now(tz=UTC) - timedelta(minutes=45)
            old_exit = datetime.now(tz=UTC) - timedelta(minutes=30)
            records = [
                {
                    "created_at_utc": old_open.isoformat(timespec="seconds"),
                    "status": "MT5_FILLED",
                    "request": {"symbol": "EURGBP", "side": "SELL"},
                    "decision": {
                        "approved": True,
                        "adjusted_notional_usd": 25_000,
                    },
                },
                {
                    "created_at_utc": old_exit.isoformat(timespec="seconds"),
                    "status": "MT5_FILLED",
                    "request": {"symbol": "EURGBP", "side": "BUY"},
                    "decision": {
                        "approved": True,
                        "adjusted_notional_usd": 0.0,
                    },
                },
            ]
            journal.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURGBP",),
                strategy_name="opportunity_probe",
                timeframe="M1",
                journal_path=str(journal),
            )
            executor = _StaticPortfolioExecutor(
                journal=journal,
                portfolio=PortfolioSnapshot(
                    positions=(Position(symbol="EURGBP", notional_usd=-10_000),)
                ),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_BalancedMomentumMarket(),
                account_adapter=_StaticAccount(),
                executor=executor,
            )

        self.assertEqual(engine._holding_periods["EURGBP"], 1)

    def test_wall_clock_quote_age_validation_blocks_stale_live_quotes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_StaleBalancedMomentumMarket(),
                account_adapter=_StaticAccount(),
                executor=DryRunExecutor(journal),
                validate_quote_age_against_wall_clock=True,
            )

            result = engine.run()

        self.assertEqual(len(result.iterations), 1)
        self.assertEqual(result.records, ())
        self.assertEqual(result.iterations[0].allocation.requested_gross_notional_usd, 0.0)

    def test_live_iteration_timestamp_uses_wall_clock_when_quote_age_is_live_checked(self) -> None:
        wall_clock = datetime(2026, 6, 22, 20, 45, tzinfo=UTC)
        broker_future_quote = QuoteSnapshot(
            timestamp=wall_clock + timedelta(hours=1),
            symbol="EURUSD",
            bid=1.09995,
            ask=1.10005,
        )

        timestamp = _iteration_timestamp(
            {"EURUSD": broker_future_quote},
            validate_quote_age_against_wall_clock=True,
            now=wall_clock,
        )

        self.assertEqual(timestamp, wall_clock)

    def test_non_live_iteration_timestamp_uses_latest_quote_timestamp(self) -> None:
        wall_clock = datetime(2026, 6, 22, 20, 45, tzinfo=UTC)
        broker_future_quote = QuoteSnapshot(
            timestamp=wall_clock + timedelta(hours=1),
            symbol="EURUSD",
            bid=1.09995,
            ask=1.10005,
        )

        timestamp = _iteration_timestamp(
            {"EURUSD": broker_future_quote},
            validate_quote_age_against_wall_clock=False,
            now=wall_clock,
        )

        self.assertEqual(timestamp, broker_future_quote.timestamp)

    def test_progress_callback_reports_successful_iterations(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
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
            callbacks = []

            result = engine.run(progress_callback=lambda *args: callbacks.append(args))

        self.assertEqual(len(result.iterations), 1)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(callbacks[0][0], 0)
        self.assertIsNotNone(callbacks[0][1])
        self.assertIsNone(callbacks[0][2])

    def test_live_throttle_blocks_new_entries_after_daily_loss(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_BalancedMomentumMarket(),
                account_adapter=_StaticAccount(equity=999_000),
                executor=DryRunExecutor(journal),
                live_risk_throttle=LiveRiskThrottle(
                    reduce_only_daily_loss_pct=0.0005
                ),
            )

            result = engine.run()

        self.assertEqual(result.records, ())
        self.assertEqual(result.iterations[0].allocation.adjusted_gross_notional_usd, 0.0)
        self.assertIn(
            "daily P/L",
            result.iterations[0].allocation.targets[0].intent_reason,
        )

    def test_live_throttle_blocks_new_entries_on_weak_rolling_sharpe(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            metrics = Path(tmpdir) / "metrics.csv"
            metrics.write_text(
                "timestamp_utc,equity,rolling_sharpe_15\n"
                "2026-06-22T12:00:00+00:00,1000000,-1.25\n",
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
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
                live_risk_throttle=LiveRiskThrottle(
                    reduce_only_rolling_sharpe=0.0,
                    metrics_csv=str(metrics),
                ),
            )

            result = engine.run()

        self.assertEqual(result.records, ())
        self.assertEqual(result.iterations[0].allocation.adjusted_gross_notional_usd, 0.0)
        self.assertIn(
            "rolling Sharpe",
            result.iterations[0].allocation.targets[0].intent_reason,
        )

    def test_live_throttle_blocks_sentiment_conflicting_new_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            sentiment = Path(tmpdir) / "sentiment.json"
            sentiment.write_text(
                json.dumps({"pairs": {"EURUSD": {"score": -1.5}}}),
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
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
                live_risk_throttle=LiveRiskThrottle(
                    sentiment_snapshot_path=str(sentiment),
                    sentiment_conflict_threshold=1.25,
                ),
            )

            result = engine.run()

        self.assertEqual(result.records, ())
        self.assertIn(
            "headline sentiment conflict",
            result.iterations[0].allocation.targets[0].intent_reason,
        )

    def test_live_throttle_sentiment_conflict_still_allows_exits(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            sentiment = Path(tmpdir) / "sentiment.json"
            sentiment.write_text(
                json.dumps({"pairs": {"EURUSD": {"score": -1.5}}}),
                encoding="utf-8",
            )
            executor = DryRunExecutor(journal)
            account = AccountSnapshot(equity=1_000_000, margin_level_pct=2_000)
            executor.submit(
                account=account,
                request=TradeRequest(
                    symbol="EURUSD",
                    side=Side.BUY,
                    target_notional_usd=50_000,
                    reason="existing position",
                ),
                decision=RiskDecision(
                    approved=True,
                    reason="seed",
                    adjusted_notional_usd=50_000,
                    state=RiskState.NORMAL,
                ),
                mode=CompetitionMode.QUALIFY,
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_FlatMarket(),
                account_adapter=_StaticAccount(),
                executor=executor,
                live_risk_throttle=LiveRiskThrottle(
                    sentiment_snapshot_path=str(sentiment),
                    sentiment_conflict_threshold=1.25,
                ),
            )

            result = engine.run()

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].decision.adjusted_notional_usd, 0.0)

    def test_live_throttle_blocks_symbol_state_new_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            states = Path(tmpdir) / "states.json"
            states.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "EURUSD": {"state": "cooldown_realized_drag"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
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
                live_risk_throttle=LiveRiskThrottle(
                    symbol_state_snapshot_path=str(states),
                ),
            )

            result = engine.run()

        self.assertEqual(result.records, ())
        self.assertIn(
            "live attribution state cooldown_realized_drag",
            result.iterations[0].allocation.targets[0].intent_reason,
        )

    def test_live_throttle_caps_small_only_symbol_state_new_entries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            states = Path(tmpdir) / "states.json"
            states.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "EURUSD": {"state": "small_only_until_recovery"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
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
                allocation_policy=AllocationPolicy(
                    max_net_directional_pct=1.0,
                    min_active_symbols=1,
                    apply_diversification_scale=False,
                ),
                live_risk_throttle=LiveRiskThrottle(
                    symbol_state_snapshot_path=str(states),
                    small_only_symbol_states=("small_only_until_recovery",),
                    small_only_max_notional_usd=25_000,
                ),
            )

            result = engine.run()

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].decision.adjusted_notional_usd, 25_000)
        self.assertIn(
            "caps fresh EURUSD risk at 25000 notional",
            result.iterations[0].allocation.targets[0].intent_reason,
        )

    def test_live_throttle_requires_cap_for_small_only_states(self) -> None:
        with self.assertRaisesRegex(ValueError, "small_only_max_notional_usd"):
            LiveRiskThrottle(
                small_only_symbol_states=("small_only_until_recovery",)
            )

    def test_live_throttle_symbol_state_still_allows_exits(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            states = Path(tmpdir) / "states.json"
            states.write_text(
                json.dumps(
                    {
                        "symbols": {
                            "EURUSD": {"state": "cooldown_realized_drag"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            executor = DryRunExecutor(journal)
            account = AccountSnapshot(equity=1_000_000, margin_level_pct=2_000)
            executor.submit(
                account=account,
                request=TradeRequest(
                    symbol="EURUSD",
                    side=Side.BUY,
                    target_notional_usd=50_000,
                    reason="existing position",
                ),
                decision=RiskDecision(
                    approved=True,
                    reason="seed",
                    adjusted_notional_usd=50_000,
                    state=RiskState.NORMAL,
                ),
                mode=CompetitionMode.QUALIFY,
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_FlatMarket(),
                account_adapter=_StaticAccount(),
                executor=executor,
                live_risk_throttle=LiveRiskThrottle(
                    symbol_state_snapshot_path=str(states),
                ),
            )

            result = engine.run()

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].decision.adjusted_notional_usd, 0.0)

    def test_live_throttle_caps_multiple_new_symbols_in_same_iteration(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD", "USDJPY"),
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
                allocation_policy=AllocationPolicy(
                    max_net_directional_pct=1.0,
                    min_active_symbols=1,
                    apply_diversification_scale=False,
                ),
                live_risk_throttle=LiveRiskThrottle(max_active_positions=1),
            )

            result = engine.run()

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.iterations[0].allocation.active_symbols, 1)
        self.assertIn(
            "active position cap",
            result.iterations[0].allocation.targets[1].intent_reason,
        )

    def test_live_throttle_still_allows_exits(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            executor = DryRunExecutor(journal)
            account = AccountSnapshot(equity=999_000, margin_level_pct=2_000)
            executor.submit(
                account=account,
                request=TradeRequest(
                    symbol="EURUSD",
                    side=Side.BUY,
                    target_notional_usd=50_000,
                    reason="existing position",
                ),
                decision=RiskDecision(
                    approved=True,
                    reason="seed",
                    adjusted_notional_usd=50_000,
                    state=RiskState.NORMAL,
                ),
                mode=CompetitionMode.QUALIFY,
            )
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_FlatMarket(),
                account_adapter=_StaticAccount(equity=999_000),
                executor=executor,
                live_risk_throttle=LiveRiskThrottle(
                    reduce_only_daily_loss_pct=0.0005
                ),
            )

            result = engine.run()

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].status, "DRY_RUN_ACCEPTED")
        self.assertEqual(result.records[0].decision.adjusted_notional_usd, 0.0)
        self.assertEqual(executor.current_portfolio().gross_notional_usd, 0.0)


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

    def test_progress_callback_reports_errors_and_recovery(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            callbacks = []
            result = self._engine(journal=journal, continue_on_error=True).run(
                progress_callback=lambda *args: callbacks.append(args)
            )
        self.assertEqual(len(result.errors), 1)
        self.assertEqual([callback[0] for callback in callbacks], [0, 1])
        self.assertIsNone(callbacks[0][1])
        self.assertIn("transient feed error", callbacks[0][2].message)
        self.assertIsNotNone(callbacks[1][1])
        self.assertIsNone(callbacks[1][2])

    def test_all_failed_iterations_report_root_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            journal = Path(tmpdir) / "journal.jsonl"
            config = load_config("configs/default.toml")
            settings = LiveDryRunSettings(
                symbols=("EURUSD",),
                strategy_name="simple_momentum",
                bars=5,
                iterations=1,
                journal_path=str(journal),
            )
            engine = LiveDryRunEngine(
                config=config,
                settings=settings,
                market_data=_FlakyMarket(),
                account_adapter=_StaticAccount(),
                executor=DryRunExecutor(journal),
            )

            with self.assertRaisesRegex(
                LiveDryRunNoSuccessfulIterationsError,
                "transient feed error",
            ):
                engine.run()

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


class _StaleBalancedMomentumMarket(_BalancedMomentumMarket):
    def __init__(self) -> None:
        super().__init__()
        stale = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        self._quotes = {
            symbol: QuoteSnapshot(
                timestamp=stale,
                symbol=quote.symbol,
                bid=quote.bid,
                ask=quote.ask,
            )
            for symbol, quote in self._quotes.items()
        }


class _FlatMarket:
    def __init__(self) -> None:
        start = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
        self._bars = {
            "EURUSD": _bars("EURUSD", (1.1000, 1.1000, 1.1000, 1.1000, 1.1000), start)
        }
        self._quotes = {
            "EURUSD": QuoteSnapshot(
                timestamp=start + timedelta(minutes=4),
                symbol="EURUSD",
                bid=1.09995,
                ask=1.10005,
            )
        }

    def supported_symbols(self) -> tuple[str, ...]:
        return ("EURUSD",)

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


class _StaticPortfolioExecutor:
    def __init__(self, *, journal: Path, portfolio: PortfolioSnapshot) -> None:
        self.journal_path = journal
        self._portfolio = portfolio

    def current_portfolio(self) -> PortfolioSnapshot:
        return self._portfolio


class _StaticAccount:
    def __init__(self, equity: float = 1_000_000) -> None:
        self.equity = equity

    def get_account_snapshot(
        self,
        *,
        starting_equity: float,
        day_start_equity: float,
        peak_equity: float,
    ) -> AccountSnapshot:
        return AccountSnapshot(
            equity=self.equity,
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
