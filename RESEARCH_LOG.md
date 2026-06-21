# QuantHack — Strategy Research Log (quanthackclaude)

Autonomous research/backtest/refine session. Goal: robust alpha + risk
discipline + hackathon-readiness against the published scoring formula:

```
Final Score = 70% Return + 15% Drawdown + 10% Sharpe + 5% Risk Discipline
```

scored **per round**, with **forced liquidation @ 30% margin level = elimination**.

**Data used:** `data/full_20gb_15m_prices.csv` / `_quotes.csv` — real 15-minute
bars, 10 instruments (8 FX + 2 metals; no crypto in this file),
2026-05-11 → 2026-06-10 (~30 days, ~2,200 bars/symbol). 15-minute granularity
matches the competition's Sharpe sampling.

All experiment harnesses live in `outputs/research/`:
`leverage_frontier.py`, `oos_walkforward.py`, `run_competition_portfolio.sh`.
Run the CLI with `PYTHONPATH=src python3.11 qh.py <command>`.

---

## 1. Per-symbol strategy baselines (in-sample `compare`)

Ran all 24 strategies per symbol. Consistent pattern:

- **Trend/momentum, low-turnover strategies win:** `macd_momentum` (most
  consistent — top/near-top on EURUSD, XAUUSD, AUDUSD, USDCHF, USDCAD),
  `multi_horizon_momentum` (GBPUSD, USDCHF), `quality_trend`, `trend_pullback`
  (XAUUSD), `volatility_squeeze` (EURGBP/EURCHF), `session_momentum` (XAGUSD).
- **High-turnover mean-reversion bleeds:** `mean_reversion` (625 fills, −0.32%),
  `breakout`/`regime_switch`/`ma_crossover` (300–430 fills, all negative). Cost
  drag from over-trading dominates any edge.
- **USDJPY** had no positive trend strategy in this window (choppy).

## 2. The dominant finding: the book was ~10–30x under-sized

Baseline portfolio (champion_ensemble, all symbols) returned **+0.27%/month** but
used a **worst leverage of only 0.53x** — under 10% of even a 6x allowance, while
the competition permits 30x and Return is 70% of the score.

Because leverage scales the mean *and* the standard deviation of 15-minute
returns equally, **Sharpe is leverage-invariant** (~0.02 throughout). So:

- **Return rank (70%)** ⇒ scale leverage up.
- **Drawdown rank (15%)** ⇒ scales up proportionally; net of the 70/15 weights,
  scaling is strongly positive while return/drawdown ≈ 2.1 (it is) — until a red
  line is hit.
- **Risk discipline (5%) / stop-out (elimination)** ⇒ the real ceilings:
  leverage <28x, margin usage <90%, single-instrument <90%, net-directional <95%.

## 3. Leverage / sizing frontier (`leverage_frontier.py`)

Best-trend-per-symbol map, sweeping the per-symbol notional cap (the actual
binding constraint — raising the *gross* cap alone did nothing; realized leverage
is set by per-symbol size × how many symbols signal at once):

| per-symbol cap | return | MaxDD | Sharpe | RD | worst lev | concentration |
|---|---|---|---|---|---|---|
| 0.10 | 0.53% | 0.25% | 0.023 | 100 | 0.73x | 68.8% |
| 0.20 | 1.06% | 0.50% | 0.023 | 100 | 1.46x | 68.8% |
| 0.40 | 2.11% | 0.99% | 0.023 | 100 | 2.91x | 68.8% |
| **0.80** | **4.22%** | **1.96%** | 0.023 | 100 | 5.74x | 68.7% |

Perfectly linear (Sharpe constant); risk discipline stays 100 and concentration /
net-directional stay flat at ~69% (scale-invariant), far from the 90/95 lines.
Per-symbol cap is hard-bounded at ≤1.0 of equity.

## 4. Out-of-sample validation (`oos_walkforward.py`) — the honest test

To kill selection bias, the per-symbol map is **chosen on the first 60%** of the
window and the frozen map is evaluated on the **held-out last 40%**:

| per-symbol cap | OOS return | OOS MaxDD | OOS Sharpe | RD | worst lev |
|---|---|---|---|---|---|
| 0.40 | +0.72% | 0.64% | 0.029 | 100 | 1.92x |
| **0.80** | **+1.44%** | **1.27%** | 0.029 | 100 | 3.85x |
| 0.90 | +1.62% | 1.43% | 0.029 | 100 | 4.33x |

The map generalizes: return/drawdown ≈ 1.13 OOS (down from ~2.1 in-sample, as
expected) but **positive, linear, and risk-clean**. This is survivable,
repeatable alpha — exactly the posture for a per-round-elimination format.

## 5. Recommended hackathon configuration

- **Config:** `configs/competition.toml` — competition-safe risk block
  (6x gross cap, 0.80 per-symbol cap, 150%/250% margin floors far above the 30%
  stop-out, a 4%→10% drawdown brake, daily-loss freeze) with per-symbol sizing
  set to the validated 0.80 operating point.
- **Strategy map (run via `outputs/research/run_competition_portfolio.sh`):**
  EURUSD/AUDUSD/USDCAD/XAUUSD/XAGUSD → `macd_momentum`;
  GBPUSD/USDCHF → `multi_horizon_momentum`;
  EURGBP/EURCHF → `volatility_squeeze`; USDJPY → `quality_trend` (low-turnover).
- **Full-data backtest of the recommended recipe:** +3.95% / MaxDD 1.96% /
  Sharpe 0.022 / **risk discipline 100/100** / worst leverage 5.28x /
  concentration 68.6% — every red line comfortably clear.

## 6. Honest caveats & next steps

- **Only ~30 days of one dataset, FX+metals only** (no crypto in this file).
  Re-select the per-symbol map and re-tune sizing on the organizer's real data
  before each round — `oos_walkforward.py` is the tool for that.
- **Sharpe (10% + the $10k Best-Sharpe prize) is the weak axis** (~0.02–0.03,
  leverage-invariant). Improving it needs *signal quality / smoother equity*, not
  sizing: candidate work = lower idle-bar variance, more consistent small-trade
  cadence, cross-sectional market-neutral overlays to cut directional noise.
- **Sizing is a risk-appetite dial.** 0.80 (≈4–6x leverage, ~1.3% OOS DD) is a
  balanced default with huge margin to the 30% stop-out; 0.90 is the aggressive
  ceiling. The coded drawdown brake de-risks automatically if a round turns bad.
- **Per-symbol map is currently a CLI argument**, not a config field. A clean
  follow-up is a `[strategy_map]` config section so the recommended portfolio is
  fully config-driven (the `strategy-map-optimize` / `adaptive-strategy-select`
  tooling already explores this space).
