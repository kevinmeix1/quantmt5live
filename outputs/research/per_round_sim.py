"""Iteration 4: per-round simulation (hackathon-rules-faithful).

The competition scores PER ROUND (daily 22:00 cuts) and eliminates the bottom
ranks each round, so the survival metric is round-by-round consistency, not the
whole-month aggregate. This slices the recommended-recipe equity curve into 24h
rounds aligned to 22:00 and computes, per round:
  * Return   = equity_end/equity_start - 1
  * MaxDD    = worst peak-to-trough within the round
  * Sharpe   = mean/std of 15-min returns (non-annualized, as the rules define);
               flagged if < 8 obs (rules cap Sharpe rank at 50 there)

Reports the distribution + consistency (how many rounds are positive, worst
round, worst round drawdown vs the 30% stop-out elimination line).

Usage: PYTHONPATH=src python3.11 outputs/research/per_round_sim.py [equity_csv]
"""
from __future__ import annotations

import csv
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "outputs" / "research" / "competition_portfolio_equity.csv")
ROUND_HOUR = 22  # daily cut at 22:00


def round_key(ts: datetime) -> datetime:
    """Start of the 22:00->22:00 round containing ts."""
    anchor = ts.replace(hour=ROUND_HOUR, minute=0, second=0, microsecond=0)
    if ts < anchor:
        anchor -= timedelta(days=1)
    return anchor


def main() -> None:
    rows = list(csv.DictReader(CSV.open()))
    rounds: dict[datetime, list[float]] = {}
    for r in rows:
        ts = datetime.fromisoformat(r["timestamp"])
        rounds.setdefault(round_key(ts), []).append(float(r["equity"]))

    print(f"Per-round simulation ({CSV.name}, 22:00 cuts, {len(rounds)} rounds)\n")
    print(f"{'round_open':>16} {'bars':>5} {'ret%':>8} {'maxDD%':>7} {'sharpe':>7} {'obs<8':>6}")
    rets, dds, sharpes, positive = [], [], [], 0
    for key in sorted(rounds):
        eq = rounds[key]
        if len(eq) < 2:
            continue
        ret = (eq[-1] / eq[0] - 1.0) * 100
        peak, mdd = eq[0], 0.0
        for e in eq:
            peak = max(peak, e)
            mdd = max(mdd, 1.0 - e / peak)
        intervals = [(eq[i] / eq[i - 1] - 1.0) for i in range(1, len(eq))]
        sd = statistics.pstdev(intervals) if len(intervals) >= 2 else 0.0
        sharpe = (statistics.fmean(intervals) / sd) if sd > 0 else 0.0
        rets.append(ret); dds.append(mdd * 100); sharpes.append(sharpe)
        positive += 1 if ret > 0 else 0
        flag = "*" if len(intervals) < 8 else ""
        print(f"{key.strftime('%Y-%m-%d %H'):>16} {len(eq):>5} {ret:>8.3f} "
              f"{mdd*100:>7.3f} {sharpe:>7.3f} {flag:>6}")

    n = len(rets)
    print("\n--- Summary (survival lens) ---")
    print(f"  rounds: {n} | positive: {positive}/{n} ({100*positive/n:.0f}%)")
    print(f"  mean round return: {statistics.fmean(rets):.3f}% | median: {statistics.median(rets):.3f}%")
    print(f"  WORST round return: {min(rets):.3f}%  (a losing round risks elimination)")
    print(f"  WORST round maxDD: {max(dds):.3f}%  (30% intra-round = forced-liquidation line)")
    print(f"  mean round Sharpe: {statistics.fmean(sharpes):.3f} | "
          f"positive-Sharpe rounds: {sum(1 for s in sharpes if s>0)}/{n}")


if __name__ == "__main__":
    main()
