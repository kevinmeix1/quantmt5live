from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.allocation_profiles import (
    ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
    allocation_policy_for_strategy,
)
from quanthack.backtesting.portfolio_universe_scan import (
    UniverseBasket,
    scan_portfolio_universes,
    write_portfolio_universe_scan_csv,
)
from quanthack.core.clock import FixedModeClock
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class PortfolioUniverseScanTest(TestCase):
    def test_scan_portfolio_universes_ranks_diversified_baskets(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"),
            periods=24,
            interval_minutes=15,
            seed=11,
        )

        scan = scan_portfolio_universes(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum", "ma_crossover"),
            min_symbols=3,
            max_symbols=4,
            max_baskets=4,
        )

        self.assertEqual(scan.available_symbols, ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"))
        self.assertEqual(scan.strategies, ("simple_momentum", "ma_crossover"))
        self.assertGreaterEqual(len(scan.baskets), 2)
        self.assertEqual(len(scan.rows), len(scan.baskets) * 2)
        self.assertIsNotNone(scan.best)
        self.assertEqual(
            [row.rank_key for row in scan.rows],
            sorted([row.rank_key for row in scan.rows], reverse=True),
        )
        for row in scan.rows:
            self.assertGreaterEqual(row.proxy_score, 0.0)
            self.assertLessEqual(row.proxy_score, 100.0)
            self.assertIn("FOREX", row.asset_mix)

    def test_custom_basket_requires_symbols_present_in_data(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=18,
            interval_minutes=15,
            seed=12,
        )

        with self.assertRaisesRegex(ValueError, "missing from data: XAUUSD"):
            scan_portfolio_universes(
                config=config,
                prices=data.prices,
                quotes=data.quotes,
                baskets=(UniverseBasket("needs_gold", ("EURUSD", "USDJPY", "XAUUSD")),),
            )

    def test_write_portfolio_universe_scan_csv(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"),
            periods=24,
            interval_minutes=15,
            seed=13,
        )
        scan = scan_portfolio_universes(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum",),
            baskets=(UniverseBasket("fx_gold", ("EURUSD", "USDJPY", "XAUUSD")),),
        )

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "universe_scan.csv"
            write_portfolio_universe_scan_csv(scan, output_path)
            csv_text = output_path.read_text(encoding="utf-8")

        self.assertIn("rank,basket,strategy,symbols,asset_mix,proxy_score", csv_text)
        self.assertIn("fx_gold", csv_text)
        self.assertIn("risk_discipline_score", csv_text)

    def test_underactive_candidates_are_demoted(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=24,
            interval_minutes=15,
            seed=14,
        )

        scan = scan_portfolio_universes(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("macd_momentum",),
            baskets=(UniverseBasket("quiet_fx", ("EURUSD", "GBPUSD", "USDJPY")),),
            min_fills=999,
        )

        self.assertEqual(len(scan.rows), 1)
        self.assertEqual(scan.rows[0].activity_status, "UNDERACTIVE")
        self.assertEqual(scan.rows[0].proxy_score, 0.0)

    def test_scan_accepts_research_clock_and_allocation_policy(self) -> None:
        config = load_config("configs/competition.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=32,
            interval_minutes=15,
            seed=15,
        )

        scan = scan_portfolio_universes(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            strategy_names=("simple_momentum",),
            baskets=(UniverseBasket("fx", ("EURUSD", "GBPUSD", "USDJPY")),),
            allocation_policy=allocation_policy_for_strategy(
                "live_research_cycle",
                config,
                profile=ALLOCATION_PROFILE_DIRECTIONAL_PROBE,
            ),
            clock=FixedModeClock(),
        )

        self.assertEqual(len(scan.rows), 1)
        self.assertEqual(scan.rows[0].basket.name, "fx")
