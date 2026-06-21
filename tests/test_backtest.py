from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.backtest import BacktestEngine, FillModel, write_equity_curve_csv
from quanthack.core.config import load_config
from quanthack.market.market_data import load_price_history, load_quote_history
from quanthack.backtesting.pnl import write_pnl_ledger_csv
from quanthack.strategies.strategy import SimpleMomentumStrategy


class BacktestTest(TestCase):
    def test_backtest_runs_and_generates_metrics(self) -> None:
        config = load_config("configs/default.toml")
        engine = BacktestEngine(
            strategy=SimpleMomentumStrategy(config.simple_momentum),
            risk_limits=config.risk,
            quality_limits=config.market_quality,
            clock=config.competition.to_clock(),
            fill_model=FillModel(slippage_bps=config.backtest.slippage_bps),
            periods_per_year=config.backtest.periods_per_year,
        )

        result = engine.run(
            prices=load_price_history(config.backtest.price_csv),
            quotes=load_quote_history(config.backtest.quote_csv),
            symbol=config.simple_momentum.symbol,
            starting_equity=config.competition.starting_equity,
        )

        self.assertEqual(result.symbol, "EURUSD")
        self.assertEqual(len(result.equity_curve), 20)
        self.assertGreater(len(result.fills), 0)
        self.assertEqual(result.metrics.observations, 20)
        self.assertGreater(result.metrics.turnover_notional, 0)
        self.assertEqual(len(result.pnl_ledger.events), len(result.fills))
        self.assertAlmostEqual(
            result.pnl_ledger.total_pnl_usd,
            result.metrics.final_equity - config.competition.starting_equity,
            places=6,
        )

    def test_equity_curve_csv_is_written(self) -> None:
        config = load_config("configs/default.toml")
        engine = BacktestEngine(
            strategy=SimpleMomentumStrategy(config.simple_momentum),
            risk_limits=config.risk,
            quality_limits=config.market_quality,
            clock=config.competition.to_clock(),
        )
        result = engine.run(
            prices=load_price_history(config.backtest.price_csv),
            quotes=load_quote_history(config.backtest.quote_csv),
            symbol=config.simple_momentum.symbol,
            starting_equity=config.competition.starting_equity,
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "equity.csv"
            write_equity_curve_csv(result, path)

            text = path.read_text(encoding="utf-8")

        self.assertIn("timestamp,close,equity", text)
        self.assertIn("position_notional_usd", text)

    def test_pnl_ledger_csv_is_written(self) -> None:
        config = load_config("configs/default.toml")
        engine = BacktestEngine(
            strategy=SimpleMomentumStrategy(config.simple_momentum),
            risk_limits=config.risk,
            quality_limits=config.market_quality,
            clock=config.competition.to_clock(),
        )
        result = engine.run(
            prices=load_price_history(config.backtest.price_csv),
            quotes=load_quote_history(config.backtest.quote_csv),
            symbol=config.simple_momentum.symbol,
            starting_equity=config.competition.starting_equity,
        )

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pnl.csv"
            write_pnl_ledger_csv(result.pnl_ledger, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("realized_pnl_usd", text)
        self.assertIn("position_units_after", text)

    def test_backtest_accepts_strategy_from_registry(self) -> None:
        config = load_config("configs/default.toml")
        engine = BacktestEngine(
            strategy=config.build_strategy("mean_reversion"),
            risk_limits=config.risk,
            quality_limits=config.market_quality,
            clock=config.competition.to_clock(),
            fill_model=FillModel(slippage_bps=config.backtest.slippage_bps),
            periods_per_year=config.backtest.periods_per_year,
        )

        result = engine.run(
            prices=load_price_history(config.backtest.price_csv),
            quotes=load_quote_history(config.backtest.quote_csv),
            symbol=config.strategy_symbol("mean_reversion"),
            starting_equity=config.competition.starting_equity,
        )

        self.assertEqual(result.symbol, "EURUSD")
        self.assertEqual(result.metrics.observations, 20)

    def test_missing_quote_fails_loudly(self) -> None:
        config = load_config("configs/default.toml")
        engine = BacktestEngine(
            strategy=SimpleMomentumStrategy(config.simple_momentum),
            risk_limits=config.risk,
            quality_limits=config.market_quality,
            clock=config.competition.to_clock(),
        )

        with self.assertRaisesRegex(ValueError, "missing quote"):
            engine.run(
                prices=load_price_history(config.backtest.price_csv),
                quotes=load_quote_history("data/sample_quotes.csv"),
                symbol=config.simple_momentum.symbol,
                starting_equity=config.competition.starting_equity,
            )
