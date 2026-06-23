from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from quanthack.backtesting.signal_diagnostics import SignalDiagnosticRow
from quanthack.market.sample_data import (
    generate_synthetic_market_data,
    write_price_history_csv,
    write_quote_history_csv,
)


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "live_research_cycle.py"
_SPEC = importlib.util.spec_from_file_location("live_research_cycle_script", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
live_research_cycle = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_research_cycle)


class LiveResearchCycleScriptTest(TestCase):
    def test_default_signal_strategies_include_router_context(self) -> None:
        self.assertEqual(
            live_research_cycle.DEFAULT_SIGNAL_STRATEGIES,
            ("champion_ensemble", "cross_rate_reversion", "alpha_router"),
        )

    def test_qualifies_signal_row_requires_activity_and_edge(self) -> None:
        row = SignalDiagnosticRow(
            symbol="EURUSD",
            signal_name="momentum",
            observations=10,
            active_count=4,
            long_count=4,
            short_count=0,
            hit_rate=0.75,
            average_signed_forward_return_bps=1.2,
            average_abs_forward_return_bps=1.4,
            average_confidence=1.0,
            average_weight=0.5,
            average_edge_after_cost_bps=0.8,
        )

        self.assertTrue(
            live_research_cycle.qualifies_signal_row(
                row,
                min_active_count=4,
                min_hit_rate=0.55,
                min_signed_bps=0.0,
                min_edge_bps=0.0,
            )
        )
        self.assertFalse(
            live_research_cycle.qualifies_signal_row(
                row,
                min_active_count=5,
                min_hit_rate=0.55,
                min_signed_bps=0.0,
                min_edge_bps=0.0,
            )
        )

    def test_main_writes_cycle_outputs(self) -> None:
        data = generate_synthetic_market_data(
            symbols=("EURUSD", "GBPUSD", "USDJPY"),
            periods=32,
            interval_minutes=15,
            seed=22,
        )
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            price_csv = root / "prices.csv"
            quote_csv = root / "quotes.csv"
            basket_csv = root / "basket.csv"
            output_json = root / "cycle.json"
            output_text = root / "cycle.txt"
            history = root / "cycle.jsonl"
            signals = root / "signals"
            write_price_history_csv(data.prices, price_csv)
            write_quote_history_csv(data.quotes, quote_csv)

            live_research_cycle.main(
                [
                    "--config",
                    "configs/default.toml",
                    "--price-csv",
                    str(price_csv),
                    "--quote-csv",
                    str(quote_csv),
                    "--symbol",
                    "EURUSD",
                    "--symbol",
                    "GBPUSD",
                    "--symbol",
                    "USDJPY",
                    "--basket",
                    "fx:EURUSD,GBPUSD,USDJPY",
                    "--basket-strategy",
                    "simple_momentum",
                    "--signal-strategy",
                    "alpha_router",
                    "--horizon-bars",
                    "1",
                    "--basket-allocation-profile",
                    "directional_probe",
                    "--force-qualify-mode",
                    "--basket-output",
                    str(basket_csv),
                    "--signal-output-dir",
                    str(signals),
                    "--output-json",
                    str(output_json),
                    "--output-text",
                    str(output_text),
                    "--history-jsonl",
                    str(history),
                ]
            )

            summary = json.loads(output_json.read_text(encoding="utf-8"))
            text = output_text.read_text(encoding="utf-8")

        self.assertEqual(summary["basket_scan"]["candidate_count"], 1)
        self.assertEqual(summary["inputs"]["basket_allocation_profile"], "directional_probe")
        self.assertTrue(summary["inputs"]["force_qualify_mode"])
        self.assertEqual(summary["signal_diagnostics"]["reports"][0]["strategy"], "alpha_router")
        self.assertIn("live_research_cycle", text)
        self.assertIn("profile=directional_probe", text)
        self.assertIn("force_qualify=true", text)
        self.assertIn("signals horizon=1", text)
