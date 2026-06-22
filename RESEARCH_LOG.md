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

## 2026-06-22 live-watch aggressive recovery checks

- Live throttle was changed from hard-blocking `small_only_until_recovery` to
  allowing capped fresh/increased targets up to 25,000 USD notional while still
  hard-blocking `cooldown_realized_drag`, `observe`, and
  `keep_if_signal_aligned`.
- Current live state after the change stayed flat: equity 999,181.58, day P/L
  -818.42, zero open positions, zero margin, and live loop `no_order`.
- `outputs/backtests/live_watch_macd_aggressive_consensus.csv` tested looser
  MACD thresholds and broader hours over W480/W672/W960. Every candidate ended
  consensus `REJECT`; extra trades hurt fold stability.
- `outputs/backtests/live_watch_recovery_symbols_strategy_map_w960.csv` tested
  EURUSD/GBPUSD-only recovery sleeves across the current strategy library. No
  map promoted; most live-capable strategies produced no fills on the full data,
  while breakout / MA / mean-reversion variants were negative or unstable.
- Best standby remains the paper-only four-symbol MACD map
  (`AUDUSD EURUSD USDCAD USDCHF`), but not live-ready by consensus. Keep the
  small-only cap active so EURUSD/GBPUSD can fire if their existing strategies
  generate a real signal, rather than forcing an unvalidated trade.

## 2026-06-22 activity-gated basket scan

- Fixed the portfolio universe scanner so zero-fill baskets are marked
  `UNDERACTIVE` and receive a zero proxy score instead of ranking as perfect
  no-drawdown candidates.
- Re-ran activity-gated full-data basket checks on the current live sleeve,
  a clean recovery sleeve, and a USD-focused sleeve. All six basket/strategy
  rows were `UNDERACTIVE` with zero fills, so none should be promoted.
- Rechecked champion ensemble squeeze-heavy variants (`squeeze_probe`,
  `squeeze_lead`) after raw diagnostics showed a few favorable
  asset-adaptive squeeze samples on GBPUSD/AUDUSD. The fixed-warmup optimizer
  still returned `REJECT` for all candidates because none produced active
  evaluation folds.

## 2026-06-22 aggressive champion near-trigger check

- Ran a full-data walk-forward champion ensemble optimization on the live
  champion symbols (`EURGBP`, `GBPUSD`) with lower entry/strong-lead thresholds
  and heavier squeeze/MACD mixes:
  `outputs/backtests/live_watch_champion_aggressive_eurgbp_gbpusd_w960.csv`.
- Result: every candidate produced zero trades and promotion `REJECT`; lowering
  ensemble entry/lead scores does not help while the component-level Kalman and
  asset-adaptive squeeze gates remain flat.
- Live config was left unchanged. Current GBPUSD near-trigger state is useful
  for monitoring, but not enough evidence to bypass the live strategy/no-change
  diagnosis or the small-only recovery cap.

## 2026-06-22 opportunity-probe and USDJPY inclusion check

- Tried a broad `opportunity_probe` symbol-eligibility search over the live FX
  sleeve; the search was stopped after exceeding the live-watch compute window,
  then replaced with a cheaper full-data attribution pass.
- `outputs/backtests/live_watch_opportunity_probe_attribution.csv` shows zero
  fills across `AUDUSD`, `EURGBP`, `EURUSD`, `GBPUSD`, `USDCAD`, `USDCHF`, and
  `USDJPY`, so re-enabling the probe is not supported by the extracted full
  dataset.
- USDJPY remains outside the live symbol list. It has the least-bad live
  realized drag, but `outputs/backtests/live_watch_usdjpy_champion_attribution.csv`
  and `outputs/backtests/live_watch_usdjpy_macd_attribution.csv` both show zero
  fills, so adding it would add risk surface without a validated signal.

## 2026-06-22 live-watch aggressive validation follow-up

- Revalidated the only positive recovery scan row, `GBPUSD/ma_crossover`, with
  a direct full-data portfolio backtest, fixed-warmup walk-forward, and current
  live strategy diagnostic:
  `outputs/backtests/gbpusd_ma_crossover_probe_*` and
  `outputs/candidate_gbpusd_ma_live_strategy_diagnostics_latest.*`.
- Result: direct full-data backtest had zero fills after shared-risk allocation,
  fixed-warmup promotion was `REJECT` with zero active evaluation folds, and
  live diagnostics requested zero exposure. Do not promote GBPUSD MA crossover.
- Ran a broad live-six attribution pass across MA, mean reversion, breakout,
  session breakout, squeeze, trend, fixing, Kalman, relative strength,
  cross-rate, MACD, and champion ensemble:
  `outputs/backtests/live_watch_broad_strategy_attribution.csv`.
  Every row had zero fills/PnL under the current full-data shared-risk setup.
- Re-ran the three nonzero volatility-squeeze screen candidates with full-data
  walk-forward validation:
  `outputs/backtests/live_watch_volatility_squeeze_live6_focused_wf.csv`.
  All three produced zero trades and zero walk-forward fills, so the earlier
  screen-only return should remain research-only, not live configuration.

## 2026-06-22 directional-probe research clock correction

- Added an explicit research-only `--force-qualify-mode` switch to portfolio
  backtest and fixed-warmup walk-forward commands. Historical full-data probes
  were otherwise evaluated before the configured live `open_at`, causing
  RiskEngine `PRE_LIVE` blocks and misleading zero-fill research.
- Re-ran the current live-watch candidates with both
  `--allocation-profile directional_probe` and `--force-qualify-mode`.
  The corrected tests now produce fills, so the research path can measure real
  P/L instead of allocator/clock artifacts.
- Results still do not justify a live promotion:
  `live_watch_asset_squeeze_top3_directional_probe_forcequal_w960_*` generated
  12 evaluation fills with 50.0% positive folds, 83.3% active folds, 66.7%
  non-negative folds, 0.005% worst drawdown, and promotion `REJECT` because the
  non-negative fold gate misses 70.0%. Champion GBPUSD/USDJPY was worse:
  14 fills, 16.7% positive folds, 33.3% non-negative folds, and `REJECT`.
- Full-period force-qualified directional-probe backtests also rejected broad
  live activation: champion on `EURGBP EURUSD GBPUSD USDJPY` lost $240.91 over
  90 fills, while MACD on `EURUSD GBPUSD USDJPY` lost $233.48 over 70 fills;
  both hit single-instrument concentration penalties. Keep these research-only.

## 2026-06-22 corrected optimizer pass-through check

- Updated the standalone MACD momentum and champion ensemble optimizers so
  research runs can pass the same `directional_probe` allocation profile and
  forced qualify-mode clock used by the live research cycle. Added parser and
  optimizer tests for the new switches.
- Full-data MACD variants on `EURUSD USDCAD USDJPY` were all `REJECT`. The
  current live MACD settings remained the least-bad row but still lost $60.72
  over 47 fills and missed the 70.0% non-negative fold gate at 66.7%.
- Full-data champion asset-heavy variants on `GBPUSD AUDUSD USDJPY` improved
  over the current champion mix but still stayed below promotion quality. The
  best asset-heavy/asset-only rows made $71.86 over 44 fills, with 83.3% active
  folds and 66.7% non-negative folds, so they remain paper/watch candidates.
- Direct `asset_adaptive_dual_squeeze` on `GBPUSD AUDUSD USDJPY` also stayed
  `REJECT`: 12 evaluation fills, 50.0% positive folds, 66.7% non-negative
  folds, and 0.005% worst drawdown. Do not lower the fold gate while live day
  P/L is negative; wait for a genuine live strategy signal or another tested
  candidate that clears robustness.

## 2026-06-22 corrected strategy-map search

- Added `--allocation-profile` and `--force-qualify-mode` support to the
  strategy-map optimizer, matching the corrected research clock/sizing path
  used by MACD, champion, universe scans, and fixed-warmup validation.
- Re-ran a full-data directional-probe map scan across `AUDUSD EURGBP EURUSD
  GBPUSD USDCAD USDCHF USDJPY` for MACD, champion, asset-adaptive squeeze,
  Kalman, cross-rate, quality trend, MA crossover, mean reversion, and
  volatility squeeze:
  `outputs/backtests/live_watch_strategy_map_corrected_directional_probe.csv`.
- The highest-return symbol mix made $696.17 over 78 fills with 0.024% max
  drawdown, but remained `REJECT` because non-negative folds were 66.7% versus
  the 70.0% promotion gate. The best robust row, `all_quality_trend`, made
  $113.77 over 35 fills with 100.0% non-negative folds, but failed promotion
  because average risk discipline was 93.3/100 versus the 95.0/100 gate.
- Added continuous supervisor diagnostics for `all_quality_trend` and the
  best-symbol mix. Current live diagnostics still request zero notional for
  both candidates; quality trend is below its 2.0 bps MACD gate and the mixed
  map is currently below squeeze/volatility thresholds. Keep both monitored,
  but do not live-promote until they request exposure and pass robustness.

## 2026-06-22 aggressive probe and squeeze/Kalman follow-up

- Re-tested `opportunity_probe` with the corrected force-qualified research
  clock on the live FX sleeve plus `USDJPY`. It remains unsuitable for live
  recovery: full-data return was -1.000% over 2,962 fills, every symbol lost
  money, fixed-warmup non-negative folds were 16.7%, and promotion was
  `REJECT`.
- Added corrected research clock/allocation pass-through for the volatility
  squeeze optimizer and portfolio walk-forward, then tested focused squeeze
  variants on `AUDUSD EURGBP EURUSD GBPUSD USDCAD`. The only positive row,
  `strict_l24_w8_r0_50_b2_5_m2`, made $227.16 over 59 fills, but walk-forward
  stability was only 16.7% and promotion remained `REJECT`.
- Added corrected research clock/allocation pass-through for the Kalman trend
  optimizer. A focused `EURGBP GBPUSD USDJPY` edge-threshold scan showed the
  current 5.0 bps edge gate is the least-bad setting. Lowering the gate to 4.0,
  3.0, or 2.5 bps increased trades and made losses worse, so do not loosen the
  Kalman edge threshold to chase current GBPUSD pair pressure.

## 2026-06-22 cross-rate follow-up

- Ran a focused cross-rate signal screen on full 15-minute data for `EURGBP`,
  `EURUSD`, `GBPUSD`, and `USDCAD`:
  `outputs/backtests/live_watch_cross_rate_focused_h4_current.csv`.
- The signal-only scan found an attractive `EURGBP` strict row with 7 active
  samples, 85.7% hit rate, 1.90 bps average signed move, and 2.43 quality
  score. This is useful as a watchlist signal, but it is not enough by itself
  to promote live trading.
- Portfolio validation rejected the idea. The strict triangle
  `EURGBP/EURUSD/GBPUSD` cross-rate portfolio produced 64 fills, ended at
  $999,699.80, returned -0.0300%, had -0.0566 Sharpe15, and reached only 33.3%
  non-negative folds. `EURGBP` alone was slightly positive, but the supporting
  legs lost enough that the portfolio remains `REJECT`.
- Keep the `EURGBP` cross-rate watchlist active, but do not switch the live map
  to `cross_rate_reversion` unless a future portfolio-level validation clears
  robustness and risk gates.
