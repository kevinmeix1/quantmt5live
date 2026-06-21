"""Leverage / sizing frontier experiment.

Runs the best-trend-per-symbol portfolio at increasing gross-leverage caps and
tabulates the competition metrics so we can pick the sizing that maximizes the
composite score (70% return + 15% drawdown + 10% sharpe + 5% risk discipline)
without risking the 30% stop-out (elimination) or the risk-discipline lines.

Usage:  PYTHONPATH=src python3.11 outputs/research/leverage_frontier.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_CONFIG = (ROOT / "configs" / "competition.toml").read_text()
PRICE = "data/full_20gb_15m_prices.csv"
QUOTE = "data/full_20gb_15m_quotes.csv"

# Best (positive, reasonable-Sharpe) trend/robust strategy per symbol, from the
# per-symbol `compare` runs on the real 15m dataset.
STRATEGY_MAP = {
    "EURUSD": "macd_momentum",
    "GBPUSD": "multi_horizon_momentum",
    "AUDUSD": "macd_momentum",
    "USDCHF": "multi_horizon_momentum",
    "USDCAD": "macd_momentum",
    "EURGBP": "volatility_squeeze",
    "EURCHF": "volatility_squeeze",
    "USDJPY": "macd_momentum",
    "XAUUSD": "macd_momentum",
    "XAGUSD": "macd_momentum",
}

METRIC_PATTERNS = {
    "return_pct": r"Official return:\s*([\-0-9.]+)%",
    "max_dd_pct": r"Official max drawdown:\s*([\-0-9.]+)%",
    "sharpe_15m": r"Official 15m Sharpe:\s*([\-0-9.]+)",
    "trades": r"Trades:\s*([0-9]+)",
    "risk_discipline": r"Risk discipline score:\s*([0-9]+)",
    "worst_leverage": r"Worst leverage:\s*([0-9.]+)x",
    "worst_net_dir": r"Worst net directional exposure:\s*([0-9.]+)%",
    "worst_conc": r"Worst largest-symbol concentration:\s*([0-9.]+)%",
}


def make_config(*, max_gross_leverage: float, target_notional: float,
                max_symbol_pct: float) -> str:
    text = BASE_CONFIG
    text = re.sub(r"max_gross_leverage = [0-9.]+",
                  f"max_gross_leverage = {max_gross_leverage}", text)
    text = re.sub(r"max_symbol_notional_pct = [0-9.]+",
                  f"max_symbol_notional_pct = {max_symbol_pct}", text)
    # Scale every strategy's sizing so the allocator's leverage cap is the
    # binding constraint rather than the per-strategy notional.
    text = re.sub(r"target_notional_usd = [0-9.]+",
                  f"target_notional_usd = {target_notional}", text)
    text = re.sub(r"max_target_notional_usd = [0-9.]+",
                  f"max_target_notional_usd = {target_notional}", text)
    return text


def run(config_text: str) -> dict[str, float]:
    cfg = ROOT / "outputs" / "research" / "_tmp_lev_config.toml"
    cfg.write_text(config_text)
    cmd = [sys.executable, "qh.py", "portfolio-backtest", "--config", str(cfg),
           "--price-csv", PRICE, "--quote-csv", QUOTE]
    for sym, strat in STRATEGY_MAP.items():
        cmd += ["--strategy-map", f"{sym}={strat}"]
    env = {"PYTHONPATH": "src", "PATH": __import__("os").environ.get("PATH", "")}
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    blob = out.stdout + out.stderr
    metrics: dict[str, float] = {}
    for key, pat in METRIC_PATTERNS.items():
        m = re.search(pat, blob)
        metrics[key] = float(m.group(1)) if m else float("nan")
    if any(v != v for v in metrics.values()):  # NaN => run failed; surface why
        tail = blob.strip().splitlines()[-3:]
        metrics["_error"] = " | ".join(tail)  # type: ignore[assignment]
    return metrics


def composite_proxy(m: dict[str, float]) -> float:
    """Rough single-entrant proxy: reward return, penalize drawdown.

    Real ranks are cross-sectional vs other entrants, but for picking sizing the
    informative quantity is return net of a drawdown penalty weighted like the
    formula (70 vs 15) plus a small sharpe term. Stop-out / discipline are veto
    gates handled separately.
    """
    return 0.70 * m["return_pct"] - 0.15 * m["max_dd_pct"] + 0.10 * (m["sharpe_15m"] * 1.0)


def main() -> None:
    # Sweep per-symbol size (the real binding constraint), gross cap high but
    # under the 28x risk-discipline line. Watch wConc (<90) and wNet (<95).
    print(f"{'sym%':>6} {'ret%':>7} {'maxDD%':>7} {'sharpe':>7} "
          f"{'trades':>6} {'RD':>4} {'wLev':>6} {'wNet%':>6} {'wConc%':>7} {'proxy':>7}")
    rows = []
    for pct in [0.10, 0.20, 0.40, 0.80, 1.50, 2.50, 4.00]:
        cfg = make_config(max_gross_leverage=26, target_notional=int(pct * 1_000_000),
                          max_symbol_pct=pct)
        m = run(cfg)
        if "_error" in m:
            print(f"{pct:>6.2f}  FAILED: {m['_error']}")
            continue
        proxy = composite_proxy(m)
        rows.append((pct, m, proxy))
        print(f"{pct:>6.2f} {m['return_pct']:>7.3f} {m['max_dd_pct']:>7.3f} "
              f"{m['sharpe_15m']:>7.3f} {int(m['trades']):>6} "
              f"{int(m['risk_discipline']):>4} {m['worst_leverage']:>6.2f} "
              f"{m['worst_net_dir']:>6.1f} {m['worst_conc']:>7.1f} {proxy:>7.3f}")
    # Best that keeps risk discipline at 100 and stays clear of the lines.
    safe = [r for r in rows if r[1]["risk_discipline"] >= 100
            and r[1]["worst_conc"] < 88 and r[1]["worst_net_dir"] < 93
            and r[1]["worst_leverage"] < 27]
    best = max(safe or rows, key=lambda r: r[2])
    print(f"\nBest safe proxy at sym%={best[0]:.2f} (return {best[1]['return_pct']:.3f}%, "
          f"maxDD {best[1]['max_dd_pct']:.3f}%, sharpe {best[1]['sharpe_15m']:.3f}, "
          f"RD {int(best[1]['risk_discipline'])}, wLev {best[1]['worst_leverage']:.2f}x)")


if __name__ == "__main__":
    main()
