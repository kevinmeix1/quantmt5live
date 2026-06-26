from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.session_momentum_optimizer import (
    SessionMomentumParameterSet,
    optimize_session_momentum_parameters,
    write_session_momentum_optimization_csv,
)
from quanthack.core.config import load_config
from quanthack.market.sample_data import generate_synthetic_market_data


class SessionMomentumOptimizerTest(TestCase):
    def test_writes_walk_forward_promotion_columns(self) -> None:
        config = load_config("configs/default.toml")
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD"),
            periods=128,
            interval_minutes=15,
            seed=901,
        )

        result = optimize_session_momentum_parameters(
            config=config,
            prices=data.prices,
            quotes=data.quotes,
            symbols=("EURUSD", "GBPUSD"),
            parameter_sets=(
                SessionMomentumParameterSet(
                    "overnight",
                    4,
                    0.5,
                    0.2,
                    0.02,
                    (0, 1, 2, 3, 4),
                ),
            ),
            include_walk_forward=True,
            train_size=48,
            test_size=24,
            step_size=24,
        )

        self.assertIsNotNone(result.candidates[0].promotion_decision)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session_momentum_opt.csv"
            write_session_momentum_optimization_csv(result, path)
            text = path.read_text(encoding="utf-8")

        self.assertIn("promotion_status,promotion_live_ready,promotion_reason", text)
