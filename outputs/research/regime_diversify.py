"""Iteration 5: regime diversification to raise per-round consistency.

The trend-only recipe is positive in only 33% of rounds (alpha concentrated in
rare trend days). Hypothesis: mixing UNCORRELATED regime exposures (trend +
mean-reversion/range + adaptive) smooths per-round PnL, raising the positive-
round fraction — the metric that actually drives per-round ranking/elimination.

Evaluates several candidate portfolios by positive-round fraction (primary),
then the chosen one is OOS-validated separately.

Usage: PYTHONPATH=src python3.11 outputs/research/regime_diversify.py
"""
from __future__ import annotations

import csv
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "outputs" / "research"
PRICE = "data/full_20gb_15m_prices.csv"
QUOTE = "data/full_20gb_15m_quotes.csv"
ENV = {"PYTHONPATH": "src", "PATH": os.environ.get("PATH", "")}

TREND = {  # baseline recipe (trend-only)
    "EURUSD": "macd_momentum", "GBPUSD": "multi_horizon_momentum",
    "AUDUSD": "macd_momentum", "USDCHF": "multi_horizon_momentum",
    "USDCAD": "macd_momentum", "EURGBP": "volatility_squeeze",
    "EURCHF": "volatility_squeeze", "XAUUSD": "macd_momentum",
    "XAGUSD": "macd_momentum", "USDJPY": "quality_trend",
}
# Regime-split: keep trend where it worked; add reversion/adaptive sleeves on the
# rest so ranging-day PnL offsets trend-day drawdowns.
REGIME_SPLIT = dict(TREND)
REGIME_SPLIT.update({
    "USDJPY": "autocorrelation_regime",   # adaptive (revert/trend by autocorr)
    "EURCHF": "mean_reversion",            # low-vol range pair
    "EURGBP": "autocorrelation_regime",
    "USDCAD": "regime_switch",
})

# Candidate portfolios: name -> ("map", dict) or ("single", strategy_name)
CANDIDATES = {
    "trend_recipe":     ("map", TREND),
    "regime_split":     ("map", REGIME_SPLIT),
    "regime_switch_all":("single", "regime_switch"),
    "alpha_router_all": ("single", "alpha_router"),
    "champion_all":     ("single", "champion_ensemble"),
    "autocorr_all":     ("single", "autocorrelation_regime"),
}


def run(name: str, kind: str, spec) -> tuple[dict, list[float]]:
    eq_csv = RES / f"_rd_{name}_equity.csv"
    cmd = [sys.executable, "qh.py", "portfolio-backtest", "--config",
           "configs/competition.toml", "--price-csv", PRICE, "--quote-csv", QUOTE,
           "--equity-output", str(eq_csv)]
    if kind == "single":
        cmd += ["--strategy", spec]
    else:
        for s, st in spec.items():
            cmd += ["--strategy-map", f"{s}={st}"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    blob = out.stdout + out.stderr
    g = lambda p: float(m.group(1)) if (m := re.search(p, blob)) else float("nan")
    agg = {"ret": g(r"Official return:\s*([\-0-9.]+)%"),
           "dd": g(r"Official max drawdown:\s*([\-0-9.]+)%"),
           "rd": g(r"Risk discipline score:\s*([0-9]+)")}
    equities = [float(r["equity"]) for r in csv.DictReader(eq_csv.open())] if eq_csv.exists() else []
    return agg, equities, eq_csv


def per_round(eq_csv: Path) -> dict:
    rows = list(csv.DictReader(eq_csv.open()))
    rounds: dict[datetime, list[float]] = {}
    for r in rows:
        ts = datetime.fromisoformat(r["timestamp"])
        anchor = ts.replace(hour=22, minute=0, second=0, microsecond=0)
        if ts < anchor:
            anchor -= timedelta(days=1)
        rounds.setdefault(anchor, []).append(float(r["equity"]))
    rets, worst = [], 0.0
    for eq in rounds.values():
        if len(eq) < 2:
            continue
        ret = eq[-1] / eq[0] - 1.0
        rets.append(ret)
        worst = min(worst, ret)
    nonflat = [r for r in rets if abs(r) > 1e-9]
    pos = sum(1 for r in rets if r > 1e-9)
    return {
        "rounds": len(rets),
        "pos_frac": pos / len(rets) if rets else 0.0,
        "pos_frac_nonflat": (sum(1 for r in nonflat if r > 0) / len(nonflat)) if nonflat else 0.0,
        "worst_round_pct": worst * 100,
        "mean_round_pct": statistics.fmean(rets) * 100 if rets else 0.0,
    }


def main() -> None:
    print(f"{'candidate':>18} {'pos%':>6} {'pos%(nonflat)':>13} {'worstRnd%':>9} "
          f"{'aggRet%':>8} {'aggDD%':>7} {'RD':>4}")
    rows = []
    for name, (kind, spec) in CANDIDATES.items():
        agg, eqs, eq_csv = run(name, kind, spec)
        pr = per_round(eq_csv)
        rows.append((name, pr, agg))
        print(f"{name:>18} {100*pr['pos_frac']:>5.0f}% {100*pr['pos_frac_nonflat']:>12.0f}% "
              f"{pr['worst_round_pct']:>9.3f} {agg['ret']:>8.3f} {agg['dd']:>7.3f} {int(agg['rd']):>4}")
    # Rank by positive-round fraction (nonflat), then aggregate return.
    rows.sort(key=lambda r: (r[1]["pos_frac_nonflat"], r[2]["ret"]), reverse=True)
    best = rows[0]
    print(f"\nMost consistent: {best[0]} — {100*best[1]['pos_frac_nonflat']:.0f}% of "
          f"non-flat rounds positive, agg {best[2]['ret']:.3f}%, worst round "
          f"{best[1]['worst_round_pct']:.3f}%")


if __name__ == "__main__":
    main()
