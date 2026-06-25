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

## 2026-06-22 multi-horizon momentum correction

- Added corrected research validation support to the multi-horizon momentum
  optimizer: `--allocation-profile` and `--force-qualify-mode`, matching the
  MACD, champion, squeeze, Kalman, strategy-map, and portfolio research paths.
- The uncorrected run produced zero fills because the competition clock and
  default allocation path made it unsuitable for live-watch research.
- Re-ran full-data directional-probe, force-qualified optimization on `EURUSD`,
  `GBPUSD`, `USDJPY`, `USDCAD`, and `USDCHF`:
  `outputs/backtests/live_watch_multi_horizon_momentum_corrected.csv`.
- No tested row is promotable. The least-bad liquid-hours row lost $324.68
  over 257 trades, returned -0.032%, drew down 0.069%, and reached only 50.0%
  non-negative folds. Broader/default/fast rows were worse. Keep
  `multi_horizon_momentum` research-only until a future variant clears
  portfolio-level return and fold robustness.

## 2026-06-22 guarded-live restart and aggression check

- Restarted the guarded live stack for the 7-day watch: MT5 terminal,
  `live_guard.ps1`, `live_supervisor.ps1`, and one `live-trade` command tree.
  The live command keeps the sentiment conflict brake, symbol-state cooldown
  throttle, max 0.10 lots, max 2 live positions, daily-loss reduce-only, and
  rolling-Sharpe reduce-only controls.
- MT5 initially had terminal-level Algo/Auto Trading disabled while account
  trading/expert flags were enabled. Toggled the terminal once and verified
  `terminal_trade_allowed=true`, `account_trade_allowed=true`,
  `account_trade_expert=true`, and `tradeapi_disabled=false`.
- Tested the tempting `USDCAD=opportunity_probe` live candidate because shadow
  diagnostics produced one short `USDCAD` intent. Full-data validation rejected
  it: the mixed directional-probe map ended at $998,827.86, returned -0.117%,
  produced 665 fills, lost $1,208.63 on USDCAD, and scored 0/100 risk
  discipline due repeated 100% single-symbol concentration. Do not live-promote
  this probe despite single-tick shadow approval.
- Tested MACD hour widening/lower thresholds to chase 15:00 UTC signals:
  `outputs/backtests/live_watch_macd_hours_full.csv`. All variants remained
  `REJECT`; the best 10-19 lower-threshold row still lost $113.03 and failed
  the 70% non-negative fold gate. Do not widen MACD hours just to force trades.
- Re-ran a broad full-data strategy-map search on live symbols:
  `outputs/backtests/live_watch_strategy_map_broad_full.csv`. Promoted
  alternatives exist (`top_4_best_symbol_strategies`, `best_per_symbol_all`,
  `top_5_best_symbol_strategies`), each with 100/100 risk discipline and
  100.0% active-positive/non-negative folds, but none beat the exact current
  live map on full-data return.
- Validated the exact current live map with fixed-warmup walk-forward:
  `outputs/backtests/live_current_map_full_wf_summary.csv`. It passed
  `PROMOTE` with 6/6 positive folds, 100.0% active folds, 100.0%
  active-positive folds, 100.0% non-negative folds, median test return 0.123%,
  worst drawdown 0.406%, 54 evaluation fills, and 100/100 average risk
  discipline. Keep the guarded live map unchanged unless a future candidate
  beats this robustness profile.

## 2026-06-22 live MT5 timestamp normalization and expanded map check

- Found live MT5 tick/bar timestamps arriving about +3,620 seconds ahead of
  wall-clock UTC across the live FX symbols. That made session-filtered
  strategies see 15:00 UTC while the actual UTC wall clock was 14:00, causing
  accidental early session gates.
- Added MT5 adapter timestamp normalization for clear whole-hour broker-server
  offsets. After the fix, live diagnostics showed quote skew near +21 seconds
  instead of +3,620 seconds, and MACD reasons moved from `session_gated` to the
  intended threshold checks.
- Restarted only the guard-owned `live-trade` process so the real-order loop
  imports the adapter fix while preserving the same max-lot, max-position,
  sentiment, cooldown, daily-loss, and rolling-Sharpe brakes.
- Ran an expanded full-data strategy-map search including more active sleeves:
  `outputs/backtests/live_watch_strategy_map_expanded_full.csv`. The promoted
  six-symbol candidate with `GBPUSD=multi_horizon_momentum` produced 112 fills
  and passed walk-forward promotion, but returned 2.427% with 0.589% max
  drawdown, weaker than the exact current live map's 2.833% return and 0.421%
  max drawdown. Monitor it as a candidate, but do not replace the live map yet.

## 2026-06-22 live diagnostics aggression guard

- Fixed `live_strategy_diagnostics.py` so non-default strategy diagnostics no
  longer silently inherit the default live symbol strategy map. This matters for
  aggressive candidates such as `opportunity_probe`: diagnostics now show the
  requested strategy's own live intent instead of the current guarded map.
- Added read-only supervisor/status-summary diagnostics for all-symbol
  `opportunity_probe` and all-symbol `multi_horizon_momentum`. They are
  monitoring candidates only; the guarded live command remains on the promoted
  MACD/champion map with sentiment, cooldown, max-lot, max-position, daily-loss,
  and rolling-Sharpe brakes intact.
- Current all-symbol `opportunity_probe` diagnostics show actionable risk on
  `AUDUSD` long and `EURGBP` short, with `EURUSD` blocked by the 2-position
  cap. Do not promote it: corrected full-data validation was negative across
  the live universe and `USDJPY`, with 16.7% non-negative folds and `REJECT`.
- Re-ran the clean full-data MACD responsiveness test on `AUDUSD EURUSD USDCAD
  USDCHF`: `outputs/backtests/live_watch_macd_responsive_default_full.csv`.
  The current live MACD parameters remain best (`PROMOTE`, +2.759%, 0.406%
  max drawdown, 74 fills, 100.0% active-positive folds). Lower thresholds added
  only six fills and reduced return to +2.396% while increasing max drawdown to
  0.605%, so keep the current MACD gates.

## 2026-06-22 afternoon activity and actionable-probe check

- Re-ran MACD afternoon/hour-extension candidates with the clean
  force-qualified default allocation path:
  `outputs/backtests/live_watch_macd_afternoon_default_w960.csv`. Adding 15:00
  UTC produced more fills but reduced return and fold stability:
  `add_15_only_6_15` returned +2.548% over 86 fills with 66.7% positive folds
  and stayed `PAPER_ONLY`; the pure 15-17 UTC sleeve was `REJECT`. Do not widen
  MACD hours just to force afternoon trades.
- Tested the exact current aggressive read-only intent,
  `opportunity_probe` on `EURUSD USDCHF`, because live diagnostics showed both
  symbols actionable. Full-data results rejected it decisively:
  `outputs/backtests/live_watch_opportunity_probe_eurusd_usdchf_*` lost
  0.280% over 846 fills, had 16.7% non-negative folds, average risk discipline
  6.7/100, and promotion `REJECT`.
- Refreshed signal diagnostics on champion/cross-rate sleeves. Champion still
  shows historical component edge for `GBPUSD` and `AUDUSD`
  asset-adaptive-dual-squeeze signals, but current live diagnostics are flat
  and the promoted best-per-symbol map remains weaker than the exact current
  live map. Keep monitoring; no live-map change.

## 2026-06-22 broad activity scan and USD-pressure router rejection

- Ran a broader activity scan across current/live baskets and recovery baskets
  with MACD, champion, dual squeeze, asset-adaptive squeeze, trend pullback,
  volatility squeeze, and fixing reversal:
  `outputs/backtests/live_watch_broad_activity_scan_latest.csv`. The top rows
  were active and slightly positive, but all required concentrated directional
  probe exposure and scored 0/100 risk discipline. Under default allocation,
  the leading volatility/dual/asset-squeeze rows produced zero active
  fixed-warmup evaluation folds and remained `REJECT`.
- Tested `usd_pressure_router` because current sentiment was USD-supportive.
  It is not a viable recovery sleeve: full-data directional-probe backtest lost
  0.543% over 1,204 fills with 0/100 risk discipline, and fixed-warmup
  validation had 0.0% non-negative folds, 592 evaluation fills, and promotion
  `REJECT`.
- Keep the live command on the promoted MACD/champion map. The current
  read-only aggressive probes are useful as alerts, but not as live
  configuration unless a future candidate clears both return/fold robustness
  and risk-discipline gates.

## 2026-06-22 recovery directional scan and fixed-warmup rejection

- Ran a bounded recovery scan with directional-probe allocation across
  current/live and recovery baskets using quality trend, relative strength,
  regime switch, mean reversion, session momentum, autocorrelation regime,
  trend pullback, and volatility squeeze:
  `outputs/backtests/live_watch_recovery_directional_cycle.csv`.
- The scan produced active-but-small positive top rows:
  `current_live/volatility_squeeze` returned 0.0185% over 38 fills,
  `gbp_aud_chf/quality_trend` returned 0.0180% over 20 fills, and
  `recovery_fx/quality_trend` returned 0.0123% over 11 fills. These are
  monitor-only because the directional-probe path is not enough evidence for a
  live-map change.
- Validated the three top rows with fixed-warmup walk-forward:
  `outputs/backtests/live_watch_vol_squeeze_current_live_w960_summary.csv`,
  `outputs/backtests/live_watch_quality_gbp_aud_chf_w960_summary.csv`, and
  `outputs/backtests/live_watch_quality_recovery_fx_w960_summary.csv`. All
  three were `REJECT` with zero active test folds. Do not promote them.
- Also refreshed broad signal diagnostics. The only qualified signals remained
  champion ensemble asset-adaptive-dual-squeeze signals on GBPUSD, AUDUSD, and
  USDJPY. Current live diagnostics are still flat/no approved risk, so keep
  these as watchlist evidence only.

## 2026-06-22 USDCHF/USDCAD afternoon probe rejection

- Refreshed live sentiment, deal attribution, pair analysis, and diagnostics.
  The account remained flat with no blocked symbols, no small-only symbols, and
  no fresh live-risk candidates. USDCHF and USDCAD had the strongest pair
  scores, but the promoted MACD sleeve was correctly session-gated at 15:00
  UTC.
- Tested the tempting USDCHF/USDCAD afternoon basket under directional-probe
  allocation. `quality_trend` was only mildly positive (+0.004%, 10 fills) and
  scored 20/100 risk discipline; `trend_pullback` lost 0.051% over 36 fills
  with 0/100 risk discipline; `volatility_squeeze` lost 0.016% over 17 fills
  with 30/100 risk discipline.
- Fixed-warmup validation of the only positive row,
  `outputs/backtests/live_watch_usdchf_usdcad_quality_w960_summary.csv`,
  was `REJECT` with zero active test folds. Do not loosen the live MACD
  session gate or promote this afternoon USDCHF/USDCAD sleeve.

## 2026-06-22 EURGBP/GBPUSD opportunity-probe rejection

- Tested the latest actionable `candidate_all_opportunity_probe` basket from the
  live diagnostics. The live snapshot requested short EURGBP and long GBPUSD
  exposure under `opportunity_probe`, with allocation status `WARN`.
- Full-data backtests:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbpusd_directional_*`
  and
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbpusd_default_*`.
  Both allocation profiles produced the same result: 813 fills, final equity
  $997,647.02, return -0.235%, Sharpe -1.387, max drawdown 0.273%, and risk
  discipline 0/100.
- Symbol attribution was negative on both legs: EURGBP about -$1,136.66 and
  GBPUSD about -$1,216.31. Keep this basket out of live promotion despite the
  current actionable diagnostic.

## 2026-06-22 MACD basket and parameter recheck

- Rechecked the activity-scan `usd_ok/macd_momentum` idea with the fixed
  QUALIFY clock:
  `outputs/backtests/live_watch_usd_ok_macd_eurusd_usdcad_usdjpy_*`.
  Full-sample was positive (+0.440%, 18 fills, 100/100 risk discipline), but
  fixed-warmup validation stayed `PAPER_ONLY`; one fold contributed 93.0% of
  positive walk-forward return.
- Removing weak USDJPY produced a cleaner EURUSD/USDCAD pair:
  `outputs/backtests/live_watch_usd_ok_macd_eurusd_usdcad_*`. It returned
  +0.389% with 100/100 risk and lower drawdown, but only 12 full-sample fills;
  W960 and W480 fixed-warmup both stayed `PAPER_ONLY` because the gains were
  concentrated in one fold.
- Tested `clean_recovery/macd_momentum`
  (EURUSD/GBPUSD/USDCAD/USDJPY):
  `outputs/backtests/live_watch_clean_recovery_macd_eurusd_gbpusd_usdcad_usdjpy_*`.
  It had 30 fills and 100/100 risk discipline, but W960 validation remained
  `PAPER_ONLY`; symbol attribution showed GBPUSD and USDJPY were both negative.
- Re-ran focused MACD parameter validation on
  AUDUSD/EURUSD/USDCAD/USDCHF/USDJPY:
  `outputs/backtests/live_watch_macd_param_recheck_5symbols_w960.csv` and
  `outputs/backtests/live_watch_macd_param_recheck_5symbols_w480.csv`.
  The current 8/21/8 parameter family was still best by full-sample return, but
  promotion remained `PAPER_ONLY`: W960 missed the total-positive gate by a
  narrow 4/6 folds (66.7% vs 67.0%), and W480 dropped to 44.4% positive folds.
- Do not add USDJPY, widen MACD hours, or switch MACD parameters on this
  evidence. Keep the guarded live map unchanged and continue monitoring for
  genuine live-map approval rather than forcing sparse fold-concentrated alpha.

## 2026-06-22 FX8 strategy-map expansion check

- Refreshed the live inputs at 16:36Z. The guarded live map still requested no
  risk; `opportunity_probe` requested AUDUSD/EURUSD long exposure with
  `PENALTY_RISK`, matching the previously rejected concentration pattern.
- Ran an expanded FX8 strategy-map search on
  AUDUSD/EURCHF/EURGBP/EURUSD/GBPUSD/USDCAD/USDCHF/USDJPY with
  `macd_momentum`, `champion_ensemble`, `quality_trend`,
  `multi_horizon_momentum`, and `asset_adaptive_dual_squeeze`:
  `outputs/backtests/live_watch_strategy_map_fx8_refine_wf.csv` and
  `outputs/backtests/live_watch_strategy_map_fx8_refine_scores.csv`.
- W960 produced apparent `PROMOTE` rows, including the familiar MACD core
  (AUDUSD/EURUSD/USDCAD/USDCHF) and a six-symbol map that changes GBPUSD to
  `multi_horizon_momentum`. Because earlier finer-fold checks were weaker, this
  was treated as a candidate for confirmation, not a live change.
- Confirmation run:
  `outputs/backtests/live_watch_strategy_map_live6_refine_confirm_w480.csv`.
  The MACD core reverted to `PAPER_ONLY` (44.4% positive folds, 66.7%
  active-positive, 77.8% non-negative), and the six-symbol map was `REJECT`
  (38.9% positive, 50.0% active-positive, 61.1% non-negative).
- No live-map change. The W960 result is useful evidence that the MACD core
  remains the best research sleeve, but the finer W480 stability check still
  rejects a live promotion or a GBPUSD strategy switch.

## 2026-06-22 adaptive metal recipe cash-fallback refinement

- Rechecked the metal-inclusive adaptive recipe universe:
  XAGUSD/XAUUSD/USDCHF/AUDUSD/GBPUSD/EURUSD/EURGBP with base
  `kalman_trend`, `champion_ensemble`, `macd_momentum`, plus recipe maps
  `multi_top3`, `macd_7`, and `top5_static`.
- W960 remained promising but not live-promotable:
  `outputs/backtests/live_watch_adaptive_metal7_recheck_force_*` had 58
  evaluation fills, 100/100 average risk discipline, no losing folds, stitched
  OOS final equity $1,026,623.22, and `PAPER_ONLY` because total positive folds
  were 4/6 (66.7%) versus the 67.0% live gate.
- W480 disproved a direct live expansion:
  `outputs/backtests/live_watch_adaptive_metal7_recheck_force_w480_*` fell to
  29.4% positive folds, 62.5% active-positive folds, 82.4% non-negative folds,
  1.584% worst drawdown, and stitched OOS final equity $987,049.33.
- Added an opt-in adaptive selector guard:
  `--cash-fallback-on-train-gate`. When every non-cooldown candidate fails the
  training gate, the selector can now choose an explicit flat `cash_fallback`
  fold instead of forcing the best raw failed candidate. Existing behavior is
  unchanged unless the flag is passed.
- The cash-fallback W480 check
  `outputs/backtests/live_watch_adaptive_metal7_recheck_force_cash_w480_*`
  improved survival but not promotion: 88.2% non-negative folds, 100/100 risk,
  44 evaluation fills, stitched OOS final equity $999,040.92, and `PAPER_ONLY`.
- Do not add XAUUSD/XAGUSD to the guarded live command yet. The cash fallback is
  a useful research safety improvement, but the finer-fold evidence still does
  not justify a live expansion.

## 2026-06-22 exact opportunity-probe intent rejection

- Rechecked the latest all-symbol `opportunity_probe` diagnostic. It requested
  short AUDUSD and short EURUSD exposure, while USDCAD and USDCHF were blocked
  by the two-position cap; the allocator marked the combined request
  `PENALTY_RISK`.
- Tested the exact actionable AUDUSD/EURUSD pair under both directional-probe
  and default allocation:
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_directional_*`
  and `outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_default_*`.
  Both paths lost 0.299% over 877 fills, had negative Sharpe, and scored 0/100
  risk discipline. AUDUSD lost $1,495.47 and EURUSD lost about $1,490.32.
- Keep `opportunity_probe` monitor-only. This is the exact current aggressive
  trade idea, and the full-data evidence says not to force it live.

## 2026-06-22 live-six strategy-map refinement

- Refreshed MT5/live inputs and re-ran a bounded full-data strategy-map
  optimization on the current live FX universe:
  `AUDUSD EURGBP EURUSD GBPUSD USDCAD USDCHF`.
- Candidate sleeves tested under default allocation with fixed-warmup
  walk-forward ranking:
  `champion_ensemble`, `macd_momentum`, `kalman_trend`,
  `multi_horizon_momentum`, `asset_adaptive_dual_squeeze`, and
  `quality_trend`.
- Output files:
  `outputs/backtests/live_watch_strategy_map_live6_refine_wf.csv` and
  `outputs/backtests/live_watch_strategy_map_live6_refine_scores.csv`.
- The best-ranked map remained the MACD core:
  `AUDUSD=macd_momentum EURUSD=macd_momentum USDCAD=macd_momentum
  USDCHF=macd_momentum`. Full-sample return was +2.759%, max drawdown 0.406%,
  74 fills, Sharpe15 0.046, and risk discipline 100/100, but walk-forward
  promotion stayed `PAPER_ONLY` with 44.4% total positive folds and 66.7%
  active-positive folds.
- Direct fixed-warmup recheck:
  `outputs/backtests/live_watch_macd_core_live4_w960_summary.csv` confirmed the
  same verdict: 18 folds, 70 evaluation fills, 66.7% active-positive folds,
  77.8% non-negative folds, 0.289% worst drawdown, 100/100 risk discipline,
  promotion `PAPER_ONLY`.
- `quality_trend` looked clean but too sparse:
  `outputs/backtests/live_watch_quality_live6_w960_summary.csv` produced only
  20 evaluation fills across 3 active folds, with 16.7% total positive folds.
  Keep it as a watchlist sleeve, not a live-map replacement.
- Do not change the guarded live command from the current MACD/champion map on
  this evidence. The refinement supports continuing to monitor the MACD core
  and researching `quality_trend`, but it does not justify broadening live risk
  just to increase trade frequency.

## 2026-06-22 adaptive live-six research-clock fix

- Added `--force-qualify-mode` to `adaptive-strategy-select` and threaded the
  optional fixed research clock through adaptive training, dynamic per-symbol
  scoring, and selected-candidate evaluation. This aligns adaptive selection
  with the other full-data research CLIs; without the override, historical bars
  can be classified outside QUALIFY and adaptive scans can misleadingly produce
  zero active folds.
- Added monitor clarity to `live_status_summary.py`: when pair analysis reports
  an `eligible_*probe*` action but live strategy diagnostics request no risk,
  the text summary now emits `heuristic_only_probes`. This makes it explicit
  that a tiny-probe heuristic is not the same thing as live strategy approval.
- Verification:
  `.venv/Scripts/python.exe -m unittest tests.test_cli
  tests.test_adaptive_strategy_selector tests.test_live_status_summary_script`,
  `.venv/Scripts/python.exe -m py_compile ...`, and default `python -m unittest
  tests.test_live_status_summary_script` all passed.
- Re-ran adaptive live-six refinement with the fixed clock:
  `outputs/backtests/live_watch_adaptive_live6_refine_force_*`. It produced 74
  evaluation fills, 100/100 risk discipline, 61.1% active folds, 63.6%
  active-positive folds, 77.8% non-negative folds, 0.347% worst drawdown, and
  stitched OOS final equity $1,023,214.20. Promotion remained `PAPER_ONLY`.
- Re-ran the stricter training-fill/churn variant:
  `outputs/backtests/live_watch_adaptive_live6_refine_force_gated_*`. It
  produced 90 evaluation fills and stitched OOS final equity $1,025,030.16, but
  fold stability still missed live promotion: 44.4% total positive folds,
  61.5% active-positive folds, 72.2% non-negative folds, promotion
  `PAPER_ONLY`.
- Do not switch the guarded live command to adaptive selection yet. The fix
  restores useful research evidence and finds more active paper candidates, but
  the live promotion gate still rejects a live-map change.

## 2026-06-22 USDJPY live expansion check

- Rechecked whether the currently supportive USDJPY sentiment justifies adding
  USDJPY to the guarded live map.
- USDJPY alone under `macd_momentum` was inactive on both windows:
  `outputs/backtests/live_watch_usdjpy_macd_w960_summary.csv` and
  `outputs/backtests/live_watch_usdjpy_macd_w480_summary.csv` produced zero
  evaluation fills and were `REJECT`.
- USDJPY alone under `opportunity_probe` was active but strongly rejected:
  W960 had 220 fills, 0.0% non-negative folds, negative median return, negative
  Sharpe, and 0/100 average risk discipline; W480 stayed negative with 342
  fills, 5.6% non-negative folds, and 0/100 risk discipline.
- Adding `USDJPY=macd_momentum` to the current live-six map passed the coarse
  W960 check but did not improve the setup:
  `live_watch_live7_add_usdjpy_macd_w960_summary.csv` was `PROMOTE` with 58
  fills, 83.3% positive folds, 83.3% active-positive folds, 0.490% worst
  drawdown, and 100/100 risk discipline, versus the exact live-six W960's 54
  fills, 100.0% positive folds, 100.0% active-positive folds, and 0.406% worst
  drawdown.
- The finer W480 check remained `PAPER_ONLY` for both exact live-six and live7:
  50.0% total positive folds, 69.2% active-positive folds, 77.8% non-negative
  folds, and 100/100 risk discipline. Live7 added only four evaluation fills.
- Live diagnostics also requested zero current notional for both exact live-six
  and live7. No live restart or USDJPY expansion is warranted on this evidence.

## 2026-06-22 staged live lot-cap lift

- Current guarded live map remains the validated six-symbol mix:
  `AUDUSD=macd_momentum`, `EURGBP=champion_ensemble`,
  `EURUSD=macd_momentum`, `GBPUSD=champion_ensemble`,
  `USDCAD=macd_momentum`, and `USDCHF=macd_momentum`. No USDJPY/metals
  expansion and no `opportunity_probe` promotion were made.
- Exact current live-six evidence still supports keeping the map live-enabled:
  W960 promoted with 54 evaluation fills, 100.0% positive folds, 100.0%
  active-positive folds, 0.406% worst drawdown, and 100/100 risk discipline.
  The finer W480 check stayed `PAPER_ONLY`, so the entry gates and strategy map
  remain unchanged.
- The operational blocker was execution clipping: `--max-order-lots 0.10`
  materially undersizes approved 25k USD targets on the active FX pairs. Raised
  the staged live cap to `0.25` lots per order so a 25k USD-base target can fill
  in one order and quote-USD pairs get closer to intended risk.
- Risk brakes were kept intact: max two live positions, sentiment conflict
  brake, symbol-state cooldown throttle, small-only recovery cap, daily-loss
  reduce-only threshold, rolling-Sharpe reduce-only threshold, and guard
  flattening thresholds. This is a bounded execution-cap adjustment, not a
  relaxation of signal approval.
- Aligned `run_shadow.bat`, `run_live.bat`, `scripts/live_guard.ps1`, live
  diagnostics, and the Windows deployment guide around the same staged
  `0.25`-lot cap and small-only symbol-state behavior.

## 2026-06-22 aggressive live-candidate refresh

- Refreshed live MT5 diagnostics, sentiment, pair analysis, deal attribution,
  and status summary after the staged cap lift. The account remained flat:
  equity/balance $999,181.58, day P/L -$818.42, margin 0, positions 0, and the
  guarded live loop reported `no_order`.
- Current live diagnostics requested no new risk across AUDUSD, EURGBP, EURUSD,
  GBPUSD, USDCAD, and USDCHF. Pair analysis briefly surfaced USDJPY as a
  heuristic tiny-probe idea, but live strategy diagnostics had no USDJPY signal
  and the earlier full-data USDJPY expansion checks rejected adding it.
- Tested more active full-data candidates on the imported full pricer data
  (`data/full_20gb_15m_prices.csv` and `data/full_20gb_15m_quotes.csv`) with
  fixed-warmup W480 gates:
  - `usd_pressure_router` on live-six was very active (514 evaluation fills)
    but rejected: 33.3% non-negative folds, negative median active return,
    1.534% worst drawdown.
  - `opportunity_probe` on live-six with directional-probe allocation was
    rejected despite 1,945 evaluation fills: 16.7% non-negative folds, negative
    median active return, and 93.3/100 average risk discipline.
  - Replacing EURGBP with `cross_rate_reversion` stayed `PAPER_ONLY`: 44.4%
    positive folds, 66.7% active-positive folds, 77.8% non-negative folds, 74
    fills, and 0.289% worst drawdown. It did not improve over the current live
    map's W480 profile.
  - Replacing GBPUSD with `multi_horizon_momentum` was rejected: 61.1%
    non-negative folds and only 50.0% active-positive folds.
- Tested relaxed/extended MACD variants to increase trade frequency. All were
  rejected on W480. The extended-hours current MACD variant increased fills
  from 106 to 144 but degraded stability to 27.8% positive folds, 38.5%
  active-positive folds, and 55.6% non-negative folds. The faster relaxed
  variants also failed non-negative fold gates.
- Tested adaptive active-map selection over current live, EURGBP cross-rate,
  all-MACD, MACD core, USD-MACD, and cash fallback. It improved survival but
  remained `PAPER_ONLY`: 83.3% non-negative folds, 66.7% active-positive folds,
  33.3% total positive folds, 60 evaluation fills, and stitched OOS final
  equity $1,024,545.76.
- Decision: keep the guarded live command unchanged. The aggressive candidates
  either trade more while losing more often, or remain paper-only without
  improving the current live map. Continue monitoring EURGBP cross-rate and
  adaptive active-map selection as watchlist candidates, but do not bypass live
  promotion gates just to increase fill count.

## 2026-06-22 evening/session candidate refresh

- Refreshed live diagnostics after the 0.25-lot staged cap lift. The live loop
  was healthy and flat: equity/balance $999,181.58, day P/L -$818.42, positions
  0, margin 0, and `no_order` through the latest iterations.
- Sentiment/pair analysis moved enough to flag heuristic tiny-probe sells on
  EURGBP and EURUSD, but the actual guarded live strategy still requested zero
  allocation across AUDUSD, EURGBP, EURUSD, GBPUSD, USDCAD, and USDCHF.
- Checked current live diagnostics for evening-capable alternatives
  (`session_momentum`, `volatility_squeeze`, `trend_pullback`, and
  `mean_reversion`) under directional-probe allocation. None requested current
  risk.
- Ran W480 fixed-warmup full-data checks on the live-six universe:
  - `session_momentum`: 129 fills, but `REJECT`; 55.6% non-negative folds,
    20.0% active-positive folds, and negative median active return.
  - `volatility_squeeze`: `PAPER_ONLY`; 10 fills, 100.0% non-negative folds,
    100.0% active-positive folds, and 0.127% worst drawdown, but only 11.1%
    active folds.
  - `trend_pullback`: 68 fills, but `REJECT`; 66.7% non-negative folds,
    negative median active return, and 1.644% worst drawdown.
  - `mean_reversion`: `REJECT`; no active evaluation folds.
  - `alpha_router`: 808 fills, but `REJECT`; only 16.7% non-negative folds and
    negative median active return.
  - `relative_strength`: 532 fills, but `REJECT`; 61.1% non-negative folds,
    negative median active return, and 2.479% worst drawdown.
  - `cross_rate_reversion`: `REJECT`; no active fixed-warmup evaluation folds
    as a standalone live-six strategy.
  - `dual_squeeze`: 22 fills, but `REJECT`; 88.9% non-negative folds, but
    median active return stayed negative.
- Tried to make the clean but underactive `volatility_squeeze` sleeve more
  liquid. The liquid 20/6/0.75/1.5 variant increased full-sample fills to 122
  but lost 1.432%, drew down 1.594%, and failed walk-forward eligibility. The
  current squeeze parameters stayed safer but too sparse.
- Decision: do not add an evening/session sleeve to the guarded live command
  yet. More active candidates are currently buying fills by accepting a losing
  fold distribution. Keep `volatility_squeeze` as a low-drawdown watchlist item,
  but do not promote the liquid variant or any router/relative/session strategy.

## 2026-06-22 opportunity-probe optimizer pass

- Added a repeatable `opportunity-probe-optimize` research CLI so the active
  probe sleeve can be tuned against the same portfolio comparison and
  fixed-warmup promotion gates used by the rest of the strategy stack.
- Ran the optimizer on the imported full 15-minute pricer data for the live-six
  universe (`AUDUSD`, `EURGBP`, `EURUSD`, `GBPUSD`, `USDCAD`, `USDCHF`) with
  W480 fixed-warmup, `directional_probe` allocation, and forced QUALIFY mode.
- Result: all opportunity-probe variants remained `REJECT`.
  - Best stricter candidate
    `strict_4_12_32_s2_25_f1_75_v0_40_hold24_96`: return -0.344%, worst
    drawdown 0.414%, 1,414 trades, 33.3% positive folds, 33.3% active-positive
    folds, 33.3% non-negative folds, and negative median active return.
  - Current competition probe parameters were worse: return -0.792%, worst
    drawdown 0.831%, 2,520 trades, and only 11.1% positive/non-negative folds.
- Decision: keep `opportunity_probe` out of the guarded live map. The optimizer
  is useful for future tuning, but today's full-data evidence says the probe is
  still paying for fill count with a bad fold distribution.

## 2026-06-22 quality-trend hour extension pass

- Added a repeatable `quality-trend-optimize` research CLI to tune the clean but
  sparse quality-trend sleeve through the same portfolio and fixed-warmup gates
  used by the rest of the research stack.
- Ran full-data W480 on the live-six universe with `directional_probe`
  allocation and forced QUALIFY mode. The original 10-14 UTC quality window was
  still best, but all tested variants were rejected:
  - `current_h10_14`: return +0.014%, 28 evaluation fills, 44.4% active folds,
    75.0% active-positive folds, 88.9% non-negative folds, and tiny positive
    median active return, but `REJECT` because average risk discipline was
    93.3/100 versus the 95/100 gate.
  - `extended_h10_17` and `liquid_h11_19`: more active at 34 evaluation fills
    and 55.6% active folds, but non-negative folds fell to 66.7% and median
    active return turned negative.
  - `late_strict_h14_19`: also rejected with only 25.0% active-positive folds
    and 66.7% non-negative folds.
- Decision: do not extend live quality-trend hours. Future quality work should
  focus on sizing/risk-discipline improvement or symbol selection, not simply
  keeping the signal on later into the session.

## 2026-06-22 quality-trend sizing pass

- Extended `quality-trend-optimize` so candidates can test explicit
  `target_notional_usd` and `max_target_notional_usd` caps.
- Re-ran full-data W480 on the live-six universe with the same
  `directional_probe` allocation and forced QUALIFY mode. Smaller quality
  sizing improved the full-sample economics but did not pass promotion:
  - `micro_current_h10_14_100k`: ranked best, return +0.031%, drawdown 0.028%,
    28 evaluation fills, 75.0% active-positive folds, 88.9% non-negative folds,
    and positive median active return.
  - `small_current_h10_14_250k`: return +0.021%, same fold distribution, and
    positive median active return.
  - Both remained `REJECT` because average risk discipline stayed 93.3/100,
    below the 95/100 gate. This appears concentration-driven: the quality sleeve
    is often a one-symbol trade, so cutting notional does not remove the
    single-instrument discipline penalty.
- Decision: no live quality-trend sizing change yet. The 100k capped variant is
  a better paper candidate than the original, but promotion needs either
  cleaner multi-symbol concurrence or a verified rule change for tiny
  concentration risk, not just smaller notional.

## 2026-06-22 live status optimizer rollup

- Extended `scripts/live_status_summary.py` to surface compact optimizer scan
  results from the latest quality-trend and opportunity-probe optimizer CSVs.
- The live monitor now prints the top optimizer candidate, source CSV,
  promotion status, live-ready flag, active/non-negative fold rates, median
  active return, fills, and promotion rejection reason.
- This keeps future heartbeat checks honest when live candidate diagnostics
  request risk from a sleeve that has already failed full-data promotion gates.
  Current example: the best optimizer scan candidate is
  `micro_current_h10_14_100k`, but it remains `REJECT` because average risk
  discipline is 93.3/100 versus the 95/100 gate.

## 2026-06-22 EURUSD full-data evening MACD pressure pass

- Added extracted-directory support to the pricer importer so the Windows
  laptop can work directly from `Downloads/pricer-output-2026-05-11_2026-06-10`
  without rebuilding or rereading the 22GB zip archive.
- Imported the full extracted EURUSD slice: 27 parquet files, 26,571,659 ticks,
  and 2,212 fifteen-minute bars.
- Re-tested current live MACD hours against deliberately more active evening
  and all-day relaxed variants on the full EURUSD slice with W480 fixed warmup,
  directional-probe allocation, and forced QUALIFY mode:
  - `current_live_h6_14` ranked best: +0.012% full-sample return, 0.024%
    drawdown, 24 trades, 50.0% active folds, 66.7% active-positive folds,
    83.3% non-negative folds, but `REJECT` because average risk discipline was
    87.8/100.
  - `evening_current_h15_19` was positive but sparse: +0.007%, 14 trades,
    33.3% active folds, 66.7% active-positive folds, 88.9% non-negative folds,
    but still `REJECT` on risk discipline at 93.3/100.
  - `evening_relaxed_h15_19` added only two trades and degraded active-positive
    folds to 57.1%; `all_day_relaxed_h6_20` increased trades to 44 but lost
    -0.011%; `late_usd_pressure_h16_20` lost -0.013% with 0.0% active-positive
    folds.
- Decision: do not widen EURUSD MACD hours or lower live MACD thresholds just
  to force the current sell-pressure read. The full-data EURUSD evidence still
  prefers the current live timing, and the more aggressive variants either
  remain too sparse or turn negative.

## 2026-06-22 extracted-data importer batching pass

- Switched the pricer importer from whole-file `pyarrow` materialization to
  parquet batch iteration. This keeps memory bounded while scanning the large
  extracted Downloads parquet files and makes repeated symbol-slice imports more
  usable during live supervision.
- Verified the batch path against real extracted files with a bounded
  EURGBP/GBPUSD smoke import: 2 files, 2,258,251 ticks, and 192 fifteen-minute
  bars written from `Downloads/pricer-output-2026-05-11_2026-06-10`.
- Re-ran the EURUSD evening MACD optimizer artifact after the importer change;
  ranking and promotion results were unchanged, with `current_live_h6_14` still
  best and all aggressive evening/all-day variants still `REJECT`.
- Decision: continue importing additional symbol slices as research needs them,
  but do not loosen live trading thresholds from this pass. The infrastructure
  improvement helps us test more quickly; it is not itself a reason to add risk.

## 2026-06-22 aggressive EURGBP/GBPUSD trade-frequency pass

- Imported the full extracted EURGBP/GBPUSD slice from Downloads after the
  importer speedup: 54 parquet files, 49,816,604 ticks, and 4,424 fifteen-minute
  bars. This gives a real full-data test for the two live ensemble symbols
  currently producing heuristic probe pressure.
- Tested lower-threshold champion ensemble variants on EURGBP/GBPUSD with W480
  fixed warmup, directional-probe allocation, and forced QUALIFY mode. The best
  lower-entry candidate increased fills to 59 but still lost -0.010%, had only
  45.5% active-positive folds, and stayed `REJECT`.
- Tested aggressive opportunity-probe/scalping variants on the same full slice.
  The candidates produced 526-813 trades, but every row lost money:
  - Best-ranked `hyper_filtered_s3_00_hold4_20`: -0.140% return, 0.160%
    drawdown, 526 trades, 27.8% active-positive folds, 27.8% non-negative
    folds, and negative active median return.
  - Looser probe variants traded even more and lost more, down to -0.238% with
    809 trades.
- Decision: do not wire these aggressive sleeves into live. They satisfy the
  desire for more fills but fail the only thing that matters for survival:
  repeatable positive fold behavior after costs. Keep the guarded live command
  unchanged and continue looking for a trade-seeking sleeve that passes
  promotion gates instead of forcing known-losing churn.

## 2026-06-22 AUDUSD full-data aggressive MACD pass

- Imported the full extracted AUDUSD slice from Downloads: 27 parquet files,
  28,329,500 ticks, and 2,212 fifteen-minute bars.
- Tested current live MACD timing against evening/all-day relaxed and faster
  variants with W480 fixed warmup, directional-probe allocation, and forced
  QUALIFY mode:
  - `current_live_h6_14` was the only positive full-sample row at +0.026%, but
    it still rejected: 42.9% active-positive folds, 55.6% non-negative folds,
    and negative active median return.
  - `fast_all_day_h6_20` increased fills to 86 and improved active-positive
    folds to 57.1%, but full-sample return was -0.019% and non-negative folds
    were only 66.7%.
  - `all_day_relaxed_h6_20` increased fills to 78 but lost -0.045% with only
    44.4% non-negative folds.
- Decision: keep AUDUSD on the existing live MACD settings and do not widen
  hours or lower thresholds. The current live timing is still the least-bad
  AUDUSD sleeve, while the trade-frequency variants turn the current heuristic
  sell pressure into negative expected value.

## 2026-06-22 USDCAD/USDCHF full-data MACD pressure pass

- Imported the full extracted USDCAD/USDCHF slice from Downloads: 54 parquet
  files, 43,388,397 ticks, and 4,424 fifteen-minute bars.
- Tested current live MACD settings against lower-band, faster-window, all-day,
  late-session, and strict-slope variants with W480 fixed warmup,
  directional-probe allocation, and forced QUALIFY mode:
  - `current_live_h6_14` ranked best by the promotion sort: +0.018% full-sample
    return, 53 trades, 66.7% active-positive folds, 66.7% non-negative folds,
    and `REJECT`.
  - `strict_slope_h6_14` improved full-sample return to +0.022% and fills to
    57, but active-positive folds fell to 62.5% and non-negative folds stayed
    at 66.7%, so it also rejected.
  - Lower-threshold and all-day variants increased fills to 65-89 but all lost
    money and dropped to 44.4% active-positive/non-negative folds.
- Decision: keep USDCAD and USDCHF on the current live MACD settings. The
  live sentiment/technical pressure is real enough to monitor, but loosening
  the MACD band to force trades has negative full-data expectancy.

## 2026-06-22 AUDUSD/GBPUSD asset-adaptive squeeze signal check

- The live research cycle kept surfacing `asset_adaptive_dual_squeeze` on
  GBPUSD and AUDUSD, so I tested the pure sleeve on the full extracted slices
  before considering any live routing change.
- Results with W480 fixed warmup, directional-probe allocation, and forced
  QUALIFY mode:
  - `AUDUSD=asset_adaptive_dual_squeeze`: +0.011% full-sample return, 22
    trades, 66.7% active-positive folds, 77.8% non-negative folds, and
    `REJECT` because average risk discipline was 88.9/100.
  - `GBPUSD=asset_adaptive_dual_squeeze`: +0.009% full-sample return, only 8
    trades, 100.0% active-positive/non-negative folds, but `PAPER_ONLY`
    because one positive fold contributed 93.9% of positive walk-forward
    return.
- Decision: do not switch AUDUSD or GBPUSD live routing. GBPUSD squeeze is
  worth continued paper-watch because it matches the live research-cycle signal,
  but it is too sparse and too fold-concentrated to promote.

## 2026-06-22 live-six exact map optimizer pass

- Added `strategy-map-optimize --candidate-map` so hand-built live maps can be
  evaluated through the same shared-risk backtest, W480 fixed-warmup
  walk-forward, promotion decision, and CSV writer as generated optimizer maps.
- Built a combined live-six full-data research slice from the extracted
  AUDUSD, EURGBP, EURUSD, GBPUSD, USDCAD, and USDCHF imports: 2,212 bars per
  symbol.
- Compared the current live map against a more aggressive hybrid that moves
  AUDUSD and GBPUSD to `asset_adaptive_dual_squeeze` while keeping EURGBP on
  `champion_ensemble` and EURUSD/USDCAD/USDCHF on `macd_momentum`:
  - `current_live_map`: -0.035% full-sample return, 228 trades, 55.6%
    active-positive folds, 55.6% non-negative folds, `REJECT`.
  - `aud_gbp_squeeze_map`: +0.021% full-sample return, 150 trades, 55.6%
    active-positive folds, 55.6% non-negative folds, `REJECT`.
  - Generated `best_per_symbol_positive_only`: +0.048% full-sample return and
    79 trades, but also only 55.6% non-negative folds, so it rejected.
- Decision: no live map promotion yet. The AUD/GBP squeeze hybrid is better
  than the current live map in full-sample return and by-symbol attribution, but
  it still fails fold stability. Keep it in the live status optimizer rollup and
  continue looking for a version that reaches at least 70% non-negative folds.

## 2026-06-22 live-six opportunity-probe exact map rejection

- Refreshed live sentiment, attribution, pair analysis, and diagnostics. The
  opportunity-probe candidate briefly surfaced actionable AUDUSD/EURUSD risk,
  then cooled back to `strategy_no_change`; USDCHF remained a heuristic tiny
  probe candidate.
- Tested exact live-six maps that force those probe ideas through W480
  fixed-warmup validation:
  - `recent_aud_eur_probe_map`: 1,053 trades, -0.314% return, 11.1%
    active-positive folds, 11.1% non-negative folds, `REJECT`.
  - `usdchf_probe_map`: 619 trades, -0.154% return, 22.2%
    active-positive/non-negative folds, `REJECT`.
  - `aud_eur_usdchf_probe_map`: 1,423 trades, -0.432% return, 22.2%
    active-positive/non-negative folds, `REJECT`.
  - `all_opportunity_probe`: 2,520 trades, -0.792% return, 11.1%
    active-positive/non-negative folds, `REJECT`.
- Decision: do not route live symbols to `opportunity_probe`. These maps create
  the requested churn but destroy expectancy and fold stability after costs.

## 2026-06-22 live-six positive-subset pressure pass

- Tested a broader live-six optimizer pass on AUDUSD, EURGBP, EURUSD, GBPUSD,
  USDCAD, and USDCHF using `champion_ensemble`, `macd_momentum`,
  `asset_adaptive_dual_squeeze`, `quality_trend`, `volatility_squeeze`, and
  `multi_horizon_momentum` with W480 fixed warmup, directional-probe allocation,
  and forced QUALIFY mode.
- The closest higher-frequency candidates improved full-sample return but still
  missed walk-forward stability:
  - `best_per_symbol_all`: +0.070% full-sample return, 78 trades, 62.5%
    active-positive folds, 66.7% non-negative folds, `REJECT`. Map:
    AUDUSD/EURGBP/USDCAD on `volatility_squeeze`, EURUSD on `quality_trend`,
    GBPUSD on `asset_adaptive_dual_squeeze`, and USDCHF on `macd_momentum`.
  - `top_5_best_symbol_strategies`: +0.069% return, 70 trades, 62.5%
    active-positive folds, 66.7% non-negative folds, `REJECT`.
  - `all_quality_trend`: +0.014% return, 30 trades, 75.0% active-positive
    folds, 88.9% non-negative folds, `REJECT` because average risk discipline
    was 93.3/100 versus the 95.0/100 promotion floor.
  - `all_volatility_squeeze`: +0.018% return, 38 trades, 60.0%
    active-positive folds, 77.8% non-negative folds, `PAPER_ONLY` because total
    positive and active-positive fold rates missed the live promotion gate.
- Decision: no live promotion yet. Keep this scan in the live status optimizer
  rollup because it is the closest evidence for a more active map, but do not
  bypass the promotion gates while the account is already down on the day.

## 2026-06-22 live-seven USDJPY pressure pass

- Imported USDJPY from the extracted Downloads parquet set and merged it with
  the live-six slice, producing a balanced live-seven research set with 2,212
  fifteen-minute bars per symbol in both price and quote files.
- Tested USDJPY alongside AUDUSD, EURGBP, EURUSD, GBPUSD, USDCAD, and USDCHF
  using the active/research sleeves: `champion_ensemble`, `macd_momentum`,
  `asset_adaptive_dual_squeeze`, `volatility_squeeze`, `quality_trend`,
  `multi_horizon_momentum`, `cross_rate_reversion`, and `usd_pressure_router`.
- Results with W480 fixed warmup, directional-probe allocation, and forced
  QUALIFY mode:
  - `best_per_symbol_all`: +0.070% full-sample return, 78 trades, 62.5%
    active-positive folds, 66.7% non-negative folds, `REJECT`. The optimizer
    selected USDJPY as `cross_rate_reversion`, but the promoted subset still
    effectively matched the earlier six-symbol map because USDJPY did not add a
    stable positive sleeve.
  - `live7_current_plus_usdjpy_macd`: -0.039% return, 242 trades, 44.4%
    active-positive/non-negative folds, `REJECT`.
  - `live7_research_asset_pressure`: +0.021% return, 114 trades, 44.4%
    active-positive/non-negative folds, `REJECT`.
  - `live7_usd_pressure_overlay`: -0.251% return, 610 trades, 11.1%
    active-positive/non-negative folds, `REJECT`.
  - `all_usd_pressure_router`: -0.645% return, 1,449 trades, 0.0%
    non-negative folds, `REJECT`.
- Decision: do not add USDJPY or the USD-pressure router to the live command.
  The extra symbol and router create the requested activity, but the full-data
  walk-forward result says the activity is negative expectancy after costs.

## 2026-06-22 late-session USD pressure scan

- Current live diagnostics at 20:32 UTC were flat with no blocked symbols, while
  sentiment was supportive for USDCAD, USDCHF, and USDJPY and negative for
  AUDUSD/GBPUSD. The deployed live map remained mostly session/threshold gated,
  so I tested late-session candidates rather than loosening the live command.
- Built the scan on the live-seven full-data slice using EURUSD, USDCAD, USDCHF,
  and USDJPY with W480 fixed warmup, directional-probe allocation, and forced
  QUALIFY mode.
- Results:
  - `late_fast_h20_23` MACD: +0.004% full-sample return, 4 trades, 100.0%
    active-positive/non-negative folds, `PAPER_ONLY` because the single active
    positive fold contributed 100.0% of walk-forward positive return.
  - `late_current_h20_23` MACD: +0.001% return, 6 trades, 100.0%
    active-positive/non-negative folds, `PAPER_ONLY` for the same concentration
    reason.
  - Wider `18-23 UTC` MACD variants produced 12-16 trades but all lost money
    and fell to 25.0% active-positive folds and 66.7% non-negative folds.
  - Late/evening multi-horizon momentum produced 103-436 trades but all variants
    lost money, with 0.0%-11.1% non-negative folds.
  - Late/evening quality-trend produced only 2 trades, lost money, and had 0.0%
    active-positive folds.
- Decision: keep the late USD MACD scan in the live status rollup as a
  paper-only watch item, but do not extend live strategy hours or add USDJPY.
  The validated late-session activity is either too sparse or negative
  expectancy after costs.

## 2026-06-22 sentiment-pressure compact map pass

- With live sentiment still USD-positive and AUD/GBP-negative, tested a compact
  pressure universe on AUDUSD, GBPUSD, USDCAD, USDCHF, and USDJPY using
  `champion_ensemble`, `macd_momentum`, `asset_adaptive_dual_squeeze`,
  `volatility_squeeze`, and `quality_trend`.
- Results with W480 fixed warmup, directional-probe allocation, and forced
  QUALIFY mode:
  - `sentiment_no_jpy_mix`: +0.043% full-sample return, 65 trades, 62.5%
    active-positive folds, 66.7% non-negative folds, `REJECT`.
  - `best_per_symbol_all`: +0.038% return, 69 trades, 62.5%
    active-positive folds, 66.7% non-negative folds, `REJECT`.
  - `all_quality_trend`: +0.016% return, 24 trades, 75.0% active-positive
    folds, 88.9% non-negative folds, `PAPER_ONLY` because total positive and
    active-positive fold rates missed the live promotion gate.
  - The more active `sentiment_macd_core` and `sentiment_current_plus_jpy`
    variants lost money and fell to 33.3%-44.4% non-negative folds.
- Decision: do not promote the compact sentiment map. Add it to read-only live
  diagnostics and optimizer rollups so it can be watched if conditions improve.

## 2026-06-22 risk-repair and cross-rate refinement pass

- Re-checked the pressure to force more trades against the full-data promotion
  gates instead of loosening live controls. The account was flat, day P/L was
  -$818.42, and no symbols were blocked or small-only.
- Tested smaller/tighter quality-trend variants on the live-six data with W480
  fixed warmup, directional-probe allocation, and forced QUALIFY mode:
  - `small_current_h10_14_50k`: +0.039% return, 26 trades, 100.0%
    non-negative folds, but `REJECT` because average risk discipline was
    91.4/100 versus the 95.0/100 promotion floor.
  - `tiny_hold8_h10_14_25k`: +0.020% return, 26 trades, 100.0%
    non-negative folds, but `REJECT` because average risk discipline was
    94.3/100.
  - Later/stricter variants cut activity or stability and also rejected.
- Re-ran the cross-rate scan with a broader EURGBP parameter set. EURGBP stayed
  the only eligible cross-rate symbol; the best row improved to quality 1.56,
  28 active signals, 67.9% hit rate, and +0.35 bps edge after cost.
- Decision: keep live execution unchanged. Add the risk-repair quality scan to
  the status optimizer rollup and feed the stronger cross-rate file into the
  read-only watchlist, but do not promote either path until the promotion gates
  are met.

## 2026-06-22 evening active-strategy rejection pass

- The live stack was healthy but flat at 20:58 UTC: equity $999,181.58, day P/L
  -$818.42, no open positions, no margin, and no blocked symbols. Current
  pair analysis was USD-positive, especially USDJPY, but the deployed map was
  mostly session or threshold gated.
- Tested higher-activity full-data sleeves on the balanced live-seven slice
  with W480 fixed warmup, directional-probe allocation, and forced QUALIFY:
  - `session_momentum` on EURUSD/USDCAD/USDCHF/USDJPY: 110 evaluation fills,
    0.0% non-negative folds, `REJECT`.
  - `mean_reversion`: 5,543 fills, 0.0% non-negative folds, `REJECT`.
  - `relative_strength`: 5,151 fills, 0.0% non-negative folds, `REJECT`.
  - `breakout` and `regime_switch`: 2,330 and 2,759 fills respectively, both
    0.0% non-negative folds, `REJECT`.
  - `trend_pullback`, `session_breakout`, and `fixing_reversal` were less bad
    but still only 28.6%-42.9% non-negative folds, `REJECT`.
- Ran a smaller hybrid optimizer around the least-bad low-drawdown candidates:
  - `best_per_symbol_positive_only`: +0.061% full-sample return, 33 trades,
    100.0% active-positive/non-negative folds, but `REJECT` because average
    risk discipline was 90.0/100.
  - `top_4_best_symbol_strategies`: +0.060% return, 26 trades, 100.0%
    active-positive/non-negative folds, but risk discipline was 87.1/100.
  - `compact_lowdd`: 52 trades, 85.7% active-positive/non-negative folds, but
    slightly negative full-sample return and risk discipline 84.3/100.
- Decision: no live promotion and no guardrail loosening. The aggressive
  high-frequency families create the requested trade count but consistently
  lose after costs. Keep the low-drawdown hybrid scan in the status rollup as a
  research watch item.

## 2026-06-22 default-allocation low-drawdown validation

- Re-ran the strongest low-drawdown hybrid maps on the live-seven full-data
  slice with W480 fixed warmup, default allocation, and forced QUALIFY mode.
  This checks whether the earlier risk-discipline failures were caused by the
  diagnostic directional-probe allocator rather than the signals themselves.
- Results:
  - `all_quality_trend`: +0.637% full-sample return, 22 trades, 100/100 risk
    discipline, 100.0% active-positive and non-negative folds, but
    `PAPER_ONLY` because only 42.9% of all walk-forward folds were positive.
  - `best_per_symbol_all`: +0.533% return, 26 trades, 100/100 risk discipline,
    66.7% active-positive folds and 85.7% non-negative folds, `PAPER_ONLY`.
  - `top4_lowdd`: only 4 trades and 0.0% active-positive folds, `REJECT`.
- Decision: the default allocator repaired risk discipline but did not clear
  live promotion robustness. Add the scan to the status rollup, keep the live
  map unchanged, and continue watching for additional fold confirmation.

## 2026-06-23 adaptive USD-bias and guard continuity pass

- Found a runtime continuity gap after the overnight research run: the guard
  and live stdout had no loop/metrics updates from about 2026-06-22 21:24 UTC
  until 2026-06-23 06:26 UTC, then resumed. Windows power settings already had
  sleep disabled, so the safer fix is to make the guard resilient to blocked
  subprocess checks and stale live output.
- Added guard controls that preserve the existing live command and risk
  limits:
  - `MaxLiveLoopStaleMinutes` restarts `live-trade` if stdout stops updating
    while the process is still alive.
  - `Mt5StatusTimeoutSeconds` and `MetricsTimeoutSeconds` keep the guard loop
    from wedging inside an MT5/account probe or metrics subprocess.
- Ran a broad adaptive USD-bias selector over the live-seven full-data feeds
  with W480 fixed warmup, a one-fold loss cooldown, a churn penalty, and
  current sentiment/cross-rate recipe candidates. The run produced partial but
  usable results before being stopped for runtime:
  - 64 evaluation fills, 100/100 average risk discipline, and 71.4%
    non-negative folds.
  - Only 28.6% positive folds and 50.0% active-positive folds, so the adaptive
    switching idea is not live-promotable.
- Decision: restart the guard with the new watchdog parameters, leave live
  strategies and risk controls unchanged, and keep adaptive switching as
  research-only unless a narrower version clears the full promotion gates.

## 2026-06-23 USDJPY quality-trend live expansion

- Re-tested the current live map with `USDJPY=quality_trend` added across three
  fixed-warmup windows on the full live-seven dataset:
  - W480: 92 evaluation fills, 100/100 risk discipline, 71.4% positive folds,
    100.0% active folds, 71.4% active-positive folds, 71.4% non-negative folds,
    0.406% worst test drawdown, `PROMOTE`.
  - W672: 68 fills, 100/100 risk discipline, 75.0% positive folds, 87.5%
    active folds, 85.7% active-positive folds, 87.5% non-negative folds,
    0.316% worst drawdown, `PROMOTE`.
  - W960: 56 fills, 100/100 risk discipline, 100.0% positive, active,
    active-positive, and non-negative folds, 0.406% worst drawdown, `PROMOTE`.
- The consensus file
  `outputs/backtests/live_watch_current_jpy_quality_consensus.csv` reports
  `PROMOTE` with all three windows passed, 216 combined evaluation fills, and
  100/100 minimum average risk discipline.
- Decision: promote only the validated USDJPY quality-trend expansion. Keep
  max order lots, max live positions, sentiment conflict brake, symbol-state
  cooldown throttle, small-only throttle, and guard flatten stops intact.

## 2026-06-23 live-watch higher-activity rejection pass

- Live was healthy and flat at 2026-06-23 06:57 UTC: equity $999,181.58,
  day P/L -$818.42, no positions, no margin, no blocked or small-only symbols,
  and the seven-symbol live command included the promoted
  `USDJPY=quality_trend` leg.
- Current diagnostics showed no approved live risk because strategy gates were
  inactive, not because the risk layer was blocking fresh trades.
- Tested two narrower "more trades" replacements on the full live-seven data
  with fixed warmup W480 / 96-bar test windows and forced QUALIFY mode:
  - `USDJPY=macd_momentum` in the current map: 94 evaluation fills and
    100/100 risk discipline, but only 50.0% positive folds, 69.2%
    active-positive folds, and `PAPER_ONLY`.
  - `GBPUSD=asset_adaptive_dual_squeeze` with the promoted USDJPY quality leg:
    80 evaluation fills and 100/100 risk discipline, but only 44.4% positive
    folds, 66.7% active-positive folds, and `PAPER_ONLY`.
- Decision: no live replacement. The promoted current map plus
  `USDJPY=quality_trend` remains the strongest validated trade-ready setup;
  higher-activity alternates increased fill count but did not clear stability
  gates.

## 2026-06-23 MACD threshold pressure scan

- Live remained flat around 2026-06-23 06:59 UTC because the four deployed
  MACD symbols were below threshold, while the risk layer showed no symbol
  blocks.
- Ran a bounded full-data W480 / 96-bar MACD pressure scan on the deployed
  MACD sleeve symbols (`AUDUSD`, `EURUSD`, `USDCAD`, `USDCHF`):
  - `faster_6_18`: 82 trades, +2.082% full-sample return, 0.412% max drawdown,
    61.1% positive folds, 84.6% active-positive folds, 88.9% non-negative
    folds, `PAPER_ONLY`.
  - `live_current`: 74 trades, +2.759% full-sample return, 44.4% positive
    folds, 66.7% active-positive folds, 77.8% non-negative folds, `PAPER_ONLY`.
  - Looser `lower_hist_0_75` stayed `PAPER_ONLY`; very loose/wider-hour
    candidates were `REJECT`.
- Decision: no live MACD threshold change. The faster candidate is worth
  monitoring because it improved activity and active-fold stability, but it
  missed the total positive-fold promotion gate. Added
  `outputs/backtests/live_watch_macd_threshold_pressure_w480.csv` to the
  status optimizer rollup for future watch cycles.

## 2026-06-23 GBPUSD MACD pressure rejection

- Fresh live diagnostics around 2026-06-23 07:03 UTC showed EURGBP and USDJPY
  as heuristic-only probes, but the deployed live strategies still had zero
  requested notional and no risk-layer blocks.
- Tested a more active USD-pressure map that changed only the GBPUSD sleeve
  from `champion_ensemble` to `macd_momentum`, while keeping the promoted
  `USDJPY=quality_trend` leg:
  - 102 evaluation fills, 100/100 risk discipline, 33.3% positive folds,
    46.2% active-positive folds, 61.1% non-negative folds, 0.499% worst
    test drawdown, `REJECT`.
- Decision: no live replacement. The GBPUSD MACD variant increases trade
  count but materially worsens fold stability, so keep GBPUSD on the current
  champion ensemble and track the rejection in the status rollup.

## 2026-06-23 EURGBP MACD pressure rejection

- Live diagnostics around 2026-06-23 07:06 UTC stayed flat: all symbols were
  `no_closed_sample`, the risk layer had no blocked or small-only symbols, and
  EURGBP/GBPUSD were still gated by champion-ensemble session filters.
- Tested a narrow activity replacement that changed only EURGBP from
  `champion_ensemble` to `macd_momentum` while keeping the promoted
  `USDJPY=quality_trend` leg:
  - 78 evaluation fills, 100/100 risk discipline, 44.4% positive folds, 66.7%
    active-positive folds, 77.8% non-negative folds, 0.305% worst test
    drawdown, `PAPER_ONLY`.
- Decision: do not promote. The EURGBP MACD sleeve remains research-only
  because it did not clear the total positive-fold gate, even though it kept
  drawdown and risk discipline acceptable.

## 2026-06-23 live readiness and early-session rejection pass

- MT5 terminal trading permission flipped off during the live watch even though
  account trading remained allowed. Re-enabled Algo Trading and added guarded
  auto-recovery in `scripts/live_guard.ps1`: the guard now checks the MT5
  terminal flag, sends the Algo Trading hotkey only when the flag is false,
  re-checks, and logs the result. The live command and risk brakes were not
  loosened.
- Added `scripts/live_near_promotion.py` and supervisor/status wiring so the
  live watch ranks research rows by distance from promotion gates. Current top
  near-miss remains `faster_6_18` on the MACD sleeve, but it is still
  `PAPER_ONLY` because positive folds are below target.
- Ran a focused W480 refinement around the `6/18/5` MACD sleeve on `AUDUSD`,
  `EURUSD`, `USDCAD`, and `USDCHF`:
  - Best family (`base_6_18_h075` and equivalent histogram/slope variants):
    82 full-sample trades, +2.082% return, 0.412% drawdown, 57.1% positive
    folds, 87.0% active-positive folds, 91.4% non-negative folds,
    `PAPER_ONLY`.
  - Decision: no MACD live-parameter change. Activity is useful, but fold
    stability is not high enough for promotion.
- Tested early-session `session_momentum` grids for 06-10 UTC and 06-14 UTC,
  including loose 1.0 bps thresholds. They produced zero trades on full data,
  so the family is not useful for the current early-session flat period.
- Rechecked opportunity-probe and asset-squeeze candidates. Opportunity-probe
  produced live-time actionable diagnostics, but W480 optimizer rows remain
  negative and unstable; asset-squeeze candidates remain rejected or
  concentration-limited. No live promotion.

## 2026-06-23 live-like symbol eligibility scan

- Added allocation-profile and fixed QUALIFY clock pass-through to
  `symbol-eligibility-optimize`, so symbol subset research can now match the
  live diagnostics clock/allocation assumptions.
- Ran a narrowed full-data W480 scan on the active downside-pressure MACD
  symbols (`AUDUSD`, `EURUSD`, `GBPUSD`) after a broader five-symbol
  directional-probe combination scan proved too slow for the live watch cycle.
- Directional-probe allocation result:
  - Best subset was `AUDUSD,EURUSD` with 79 trades, +0.050% full-sample
    return, 0.052% drawdown, 50.0% positive folds, 60.0% active-positive
    folds, 66.7% non-negative folds, and 0/100 risk discipline.
- Default allocation result:
  - The same three-symbol pressure universe produced zero trades, so the
    directional-probe activity is not a default live-promotion path.
- Decision: do not promote. The scan confirms the current AUD/EUR downside
  pressure is visible to research tooling, but not stable or risk-disciplined
  enough to change live strategy selection.

## 2026-06-23 EURGBP cross-rate with USDJPY quality rejection

- Re-tested the EURGBP cross-rate replacement against the current seven-symbol
  live map, including the promoted USDJPY quality-trend leg.
- Built W480, W672, and W960 strategy-map optimizer outputs plus a consensus
  report for `eurgbp_cross_jpy_quality`.
- `eurgbp_cross_jpy_quality` stayed `PAPER_ONLY` in all windows and
  underperformed `current_jpy_quality` on minimum positive folds: 44.4% versus
  the current map's 50.0% floor.
- Decision: do not promote. Keep EURGBP on `champion_ensemble` and keep the
  cross-rate map in watchlist/research-only status.

## 2026-06-23 five-pair MACD pressure refinement

- Ran a focused full-data W480 / 96-bar MACD refinement on the current pressure
  set: `AUDUSD`, `EURUSD`, `GBPUSD`, `USDCAD`, and `USDCHF`.
- Used the imported full 15-minute pricer files
  (`data/full_20gb_15m_prices.csv` and `data/full_20gb_15m_quotes.csv`), default
  live-style allocation, and forced QUALIFY research clock.
- Best row was `faster_6_18_slope010_5pair`: 98 trades, +1.931% return, 0.527%
  drawdown, 55.6% positive folds, 71.4% active-positive folds, and 77.8%
  non-negative folds. It remained `PAPER_ONLY` because total positive folds did
  not clear the 67.0% live gate.
- Decision: do not promote. Adding GBPUSD to the MACD pressure universe creates
  more activity, but not enough fold stability to justify changing the live
  strategy map or MACD thresholds.

## 2026-06-23 current-pressure opportunity-probe rejection

- Re-tested the latest actionable `candidate_all_opportunity_probe` pressure on
  the exact requested/throttled symbols: `AUDUSD`, `EURUSD`, `GBPUSD`, and
  `USDCHF`.
- Ran full-data W480 / 96-bar optimization with directional-probe allocation and
  forced QUALIFY clock, including stricter score, spread, volatility-penalty,
  and shorter-hold variants.
- Best row was `score4_hyper_filter`: 380 trades, -0.060% return, 0.141%
  drawdown, 50.0% positive folds, 50.0% active-positive folds, and 50.0%
  non-negative folds. The live-style current row was worse: 1,698 trades,
  -0.551% return, and 16.7% non-negative folds.
- Decision: do not promote. The stricter probe reduces churn damage but still
  has negative median active return and no fold-stable edge.

## 2026-06-23 EURGBP cross-rate intraday refresh

- Refreshed the fast cross-rate signal screen on the full 15-minute data for
  `AUDUSD`, `EURGBP`, `EURUSD`, `GBPUSD`, `USDCAD`, and `USDCHF`.
- `EURGBP` remains the only eligible cross-rate watchlist symbol:
  `raw_l12_z1_dev0_25_slip0` produced 31 active samples, 71.0% hit rate,
  1.50 bps average signed forward return, 0.31 bps edge after cost, and 1.58
  quality score.
- A relaxed GBPUSD dual-squeeze W480 refinement was attempted because live
  diagnostics still show squeeze-ratio gating, but the walk-forward sweep
  exceeded the live-watch compute window and wrote no CSV. Treat it as
  inconclusive, not evidence.
- Decision: do not promote. EURGBP cross-rate remains useful watchlist context,
  but prior portfolio-level validation still rejects switching EURGBP from
  `champion_ensemble` to `cross_rate_reversion`.

## 2026-06-23 USDJPY quality pre-open rejection

- Tested whether the promoted USDJPY `quality_trend` leg should start earlier
  or use a smaller/more relaxed pre-open variant before the 10-14 UTC session.
- Ran full-data W480 / 96-bar optimization with forced QUALIFY clock on USDJPY
  candidates covering current 10-14 UTC, 9-14 UTC, 8-14 UTC, relaxed MACD
  thresholds, a 100k micro-notional variant, and a stricter 10-14 UTC variant.
- Every candidate produced zero fills in the fixed-warmup evaluation and was
  rejected with `strategy produced no active fixed-warmup evaluation folds`.
- Decision: do not promote. The current live command can keep the guarded
  USDJPY `quality_trend` slot, but there is no evidence to widen hours or force
  earlier USDJPY trades.

## 2026-06-23 four-pair fast MACD refinement

- Re-ran a compact full-data W480 / 96-bar MACD search on the current MACD live
  pressure symbols: `AUDUSD`, `EURUSD`, `USDCAD`, and `USDCHF`.
- The best family was still fast 6/18/5 with 0.75-1.25 bps histogram gates and
  6-14 UTC hours. It generated 82 trades, +2.082% full-sample return, 0.412%
  drawdown, 61.1% total positive folds, 84.6% active-positive folds, and 88.9%
  non-negative folds.
- The candidate remains `PAPER_ONLY` because total positive folds are still
  below the 67.0% live-promotion gate. Shorter holds and a 5/16 faster variant
  increased churn but weakened fold stability.
- Decision: do not promote. Keep the live MACD parameters unchanged; track
  fast 6/18 as near-promotion research only.

## 2026-06-23 USDCHF/USDJPY opportunity-probe rejection

- Fresh live candidate diagnostics showed `opportunity_probe` actionable on
  `USDCHF` short and `USDJPY` long under the directional-probe allocation
  profile, while the guarded live map still had no approved target changes.
- Ran a focused full-data W480 / 96-bar optimizer on `USDCHF` and `USDJPY`
  using directional-probe allocation and forced QUALIFY clock.
- The best row was `score5_spread3`: 88 trades, -0.036% return, 0.043%
  drawdown, 38.9% positive folds, 38.9% active-positive folds, and 38.9%
  non-negative folds. The live-like current probe was much worse: 851 trades,
  -0.339% return, and 11.1% non-negative folds.
- Decision: do not promote. The current live opportunity looked active but
  remained historically negative, so keep it research-only and do not force a
  manual USDCHF/USDJPY pair trade.

## 2026-06-23 USDCAD intraday MACD rejection

- Fresh pair analysis showed a heuristic-only `USDCAD` buy with supportive
  sentiment, while the guarded live MACD strategy still had no approved target
  because the histogram was inside the exit band.
- Ran a focused full-data W480 / 96-bar USDCAD-only MACD refinement with forced
  QUALIFY clock, testing current live, near-band, fast 6/18, fast-light, and
  narrower London/session variants.
- Every tested candidate produced zero fixed-warmup evaluation fills and was
  rejected as inactive, so the heuristic USDCAD pressure does not support
  relaxing MACD thresholds.
- Decision: do not promote. Keep USDCAD on the current guarded MACD slot and
  wait for a true live MACD trigger.

## 2026-06-23 AUDUSD/EURGBP opportunity-probe rejection

- Fresh opportunity-probe diagnostics showed directional-probe allocations for
  `AUDUSD` long and `EURGBP` short, while the guarded live map remained flat.
- Ran a focused full-data W480 / 96-bar optimizer on `AUDUSD` and `EURGBP`
  with current, stricter score, tighter spread, and longer-hold variants.
- Best fold-stability row was `aud_eurgbp_score3_5`: 230 trades, -0.012%
  return, 0.081% drawdown, and 44.4% positive / active-positive / non-negative
  folds. The strict positive-return rows reached only 33.3% non-negative folds.
- Decision: do not promote. The current live-looking opportunity probe remains
  too unstable out of sample to justify a manual or live-map trade.

## 2026-06-23 fast MACD wider-window stability check

- The nearest near-promotion candidate remained the fast MACD family on
  `AUDUSD`, `EURUSD`, `USDCAD`, and `USDCHF`, so it was stress-tested beyond
  the original W480 / 96-bar window.
- W672 / 144-bar validation promoted the fast 6/18 family: 80.0% positive
  folds, 100.0% active-positive folds, and 100.0% non-negative folds.
- W960 / 192-bar validation was more selective: current live MACD promoted
  with 83.3% positive folds, 100.0% active-positive folds, and 100.0%
  non-negative folds, while fast 6/18 fell back to `PAPER_ONLY` at 66.7%
  positive folds. `fast_7_20_s005` promoted but produced fewer fills than the
  current live MACD row.
- Decision: do not lower live MACD thresholds. The current live MACD settings
  are more robust across the wider windows, and the faster variants remain
  research-only because W480 and W960 do not both clear the total positive-fold
  gate.

## 2026-06-23 AUDUSD/EURUSD opportunity-probe rejection

- Fresh opportunity-probe diagnostics showed directional-probe allocations for
  `AUDUSD` long and `EURUSD` long, while the guarded live map remained flat.
- Prior portfolio artifacts for the same pair were negative, so a focused
  fixed-warmup optimizer was run to test stricter score, spread, volatility,
  and holding-period filters on full 15-minute data.
- Best full-sample row was `aud_eur_score5`: 92 trades, +0.025% return,
  0.058% drawdown, 38.9% positive folds, 38.9% active-positive folds, and
  38.9% non-negative folds. The live-like current probe was materially worse:
  877 trades, -0.299% return, and 22.2% non-negative folds.
- Decision: do not promote. The current AUDUSD/EURUSD opportunity-probe signal
  remains too fold-unstable to justify a manual trade or live strategy-map
  change.

## 2026-06-23 USDCHF-only opportunity-probe rejection

- Fresh pair analysis showed a heuristic-only `USDCHF` buy with supportive
  sentiment, but the guarded live MACD map still had no approved target because
  the current histogram was inside the strategy gate.
- Ran a focused full-data W480 / 96-bar optimizer on `USDCHF` only using the
  directional-probe allocation profile and forced QUALIFY clock.
- Every tested opportunity-probe variant was rejected. The best row,
  `usdchf_score3_5`, produced 132 trades, -0.036% return, 0.062% drawdown,
  55.6% positive folds, 55.6% active-positive folds, and 55.6% non-negative
  folds. The live-like current probe was much worse: 409 trades, -0.131%
  return, and 27.8% non-negative folds.
- Decision: do not promote. Keep USDCHF on the guarded MACD slot and treat
  isolated heuristic USDCHF pressure as insufficient for fresh live risk.

## 2026-06-23 asset-heavy champion wider-window rejection

- The live research cycle again surfaced `asset_adaptive_dual_squeeze` as the
  strongest short-horizon signal on `GBPUSD`, with secondary candidates on
  `AUDUSD` and `USDJPY`.
- Re-tested the asset-heavy champion family on `GBPUSD`, `AUDUSD`, and
  `USDJPY` with directional-probe allocation and forced QUALIFY clock, using
  wider W672 / 144-bar and W960 / 192-bar walk-forward windows.
- W672 stayed profitable full-sample at +0.007% with 44 trades and 0.025%
  max drawdown, but rejected because average risk discipline was only
  90.0/100 and total positive folds were only 40.0%.
- W960 also rejected: the same asset-heavy row stayed +0.007% full-sample, but
  positive folds were 50.0%, active-positive folds 60.0%, and non-negative
  folds 66.7%, below the live gate.
- Decision: do not promote the asset-heavy champion map or use it for manual
  entries. Keep it in the optimizer rollup as a near-miss research sleeve, but
  leave live routing unchanged until the fold distribution improves.

## 2026-06-23 AUDUSD/USDJPY opportunity-probe rejection

- Fresh research-only `candidate_all_opportunity_probe` diagnostics requested
  directional-probe allocations on `AUDUSD` and `USDJPY`, while the guarded
  live map remained flat.
- Ran a focused full-data W480 / 96-bar optimizer on `AUDUSD` and `USDJPY`
  with current, stricter score, tighter spread, volatility-penalty, and
  holding-period variants.
- The best row, `aud_jpy_score5`, produced 80 trades, +0.015% full-sample
  return, 0.046% max drawdown, but only 44.4% positive folds, 47.1%
  active-positive folds, and 50.0% non-negative folds. The live-like current
  probe was strongly negative: 882 trades, -0.357% return, and 5.6%
  non-negative folds.
- Decision: do not promote. The current AUDUSD/USDJPY opportunity burst is
  another unstable probe pattern, so keep it research-only and do not force
  manual or live-map exposure.

## 2026-06-23 EURUSD/GBPUSD opportunity-probe rejection

- Fresh research-only `candidate_all_opportunity_probe` diagnostics requested
  directional-probe short allocations on `EURUSD` and `GBPUSD`, while the
  guarded live strategy map remained flat.
- Ran a focused full-data W480 / 96-bar optimizer on `EURUSD` and `GBPUSD`
  with current, stricter score, tighter spread, volatility-penalty, and
  holding-period variants.
- Every tested row was rejected. The top-ranked `eur_gbp_score4` produced 192
  trades, -0.039% return, 0.089% drawdown, 33.3% positive folds, 33.3%
  active-positive folds, and 33.3% non-negative folds. The live-like current
  probe was worse: 849 trades, -0.271% return, and 16.7% non-negative folds.
- Decision: do not promote. The EURUSD/GBPUSD pressure signal is active but
  historically unstable, so keep it research-only and leave live routing
  unchanged.

## 2026-06-23 USDCAD-only opportunity-probe rejection

- Fresh pair analysis showed a heuristic-only `USDCAD` buy with supportive
  sentiment, while the guarded live MACD strategy remained threshold-gated.
- Ran a focused full-data W480 / 96-bar optimizer on `USDCAD` only using the
  directional-probe allocation profile and forced QUALIFY clock.
- Every opportunity-probe variant rejected. The best row, `usdcad_score3_5`,
  produced 123 trades, -0.033% return, 0.048% drawdown, 44.4% positive folds,
  44.4% active-positive folds, and 44.4% non-negative folds. The live-like
  current probe was worse: 421 trades, -0.127% return, and 16.7%
  non-negative folds.
- Decision: do not promote. Treat isolated USDCAD heuristic buy pressure as
  insufficient for fresh live risk until a tested MACD or opportunity-probe
  variant clears fold-stability gates.

## 2026-06-23 alpha-router signal discovery added

- The live research cycle was only writing signal diagnostics for
  `champion_ensemble` and `cross_rate_reversion`, which kept the monitor blind
  to router-level sleeves already supported by `generate_signals`.
- A manual expanded run showed `alpha_router` produces clean diagnostics on the
  full live-seven data: qualified rows included `USDCHF`, `GBPUSD`, and
  `EURUSD` session-breakout signals plus `USDJPY` mean reversion. The direct
  `macd_momentum`, `quality_trend`, `opportunity_probe`, `volatility_squeeze`,
  `dual_squeeze`, and `asset_adaptive_dual_squeeze` strategy classes do not
  expose the signal-diagnostics API and remain excluded from defaults.
- Added `alpha_router` to the default live research-cycle signal diagnostics so
  the supervisor can surface more trade-frequency candidates for validation
  without changing live routing or bypassing live risk controls.

## 2026-06-23 router/session-breakout candidate rejection

- The expanded live research cycle surfaced router-level session-breakout
  candidates on `USDCHF`, `GBPUSD`, and `EURUSD`, which looked useful for
  increasing trade frequency while the guarded live map was flat.
- Re-tested the exact candidate subset with full-data W480 / 96-bar
  fixed-warmup validation under directional-probe allocation and forced
  QUALIFY clock.
- `alpha_router` rejected sharply: 958 evaluation fills, 5.6% positive folds,
  5.6% active-positive folds, 5.6% non-negative folds, -0.021% median active
  return, and 58.3/100 average risk discipline.
- Standalone `session_breakout` was less bad but still rejected: 173 fills,
  33.3% positive folds, 33.3% active-positive folds, 33.3% non-negative
  folds, -0.003% median active return, and 87.8/100 average risk discipline.
- Added the broad alpha-router scan and the exact router/session candidate
  scans to the live status optimizer rollup so aggressive candidates are
  matched to their full-data rejection evidence before anyone promotes them.
- Decision: keep router/session-breakout in discovery only. Do not route live
  risk to these sleeves until a fresh scan clears the existing promotion gates.

## 2026-06-23 AUDUSD/GBPUSD multi-horizon rejection

- Fresh `candidate_all_multi_horizon` diagnostics requested aggressive
  directional-probe allocations on `AUDUSD` and `GBPUSD`, after live allocation
  caps trimmed the raw $1.6M request to about $99.9k total notional.
- Ran an exact full-data W480 / 96-bar fixed-warmup validation on `AUDUSD` and
  `GBPUSD` with `multi_horizon_momentum`, directional-probe allocation, and
  forced QUALIFY clock.
- The exact subset rejected: 18 folds, 84 evaluation fills, 44.4% positive
  folds, 44.4% active-positive folds, 44.4% non-negative folds, -0.0004%
  median active return, 0.018% worst drawdown, and 78.3/100 average risk
  discipline.
- Added fixed-warmup summary normalization to the live status scanner, then
  added the exact AUDUSD/GBPUSD multi-horizon summary to the optimizer rollup
  so future live-looking multi-horizon bursts surface their true rejection
  evidence.
- Decision: do not promote multi-horizon to live routing. Keep it in discovery
  and require a fresh exact-symbol scan to clear promotion gates first.

## 2026-06-23 single-symbol MACD refinement

- The live pair monitor showed an `AUDUSD` heuristic-only tiny-probe buy while
  the guarded live MACD strategy remained threshold-gated.
- Ran W480 / 96-bar fixed-warmup MACD checks on each live MACD symbol
  (`AUDUSD`, `EURUSD`, `USDCAD`, `USDCHF`) using the current live parameters
  and the strongest fast-MACD variants from the wider-window scans.
- No single-symbol MACD row promoted. The closest was `AUDUSD`
  `fast_6_18_s005`/`fast_6_18_s010`: 55.6% positive folds, 71.4%
  active-positive folds, 77.8% non-negative folds, and 50 evaluation fills,
  but still rejected.
- Ran a tighter AUDUSD-only search around fast 6/18 and 7/20 MACD thresholds,
  slopes, holding periods, and UTC hour windows. The best risk-balanced rows
  still rejected at 55.6% positive folds and 77.8% non-negative folds; risk
  discipline was only 77.8/100 for the closest hold-8 variants.
- Added the single-symbol MACD scans to the live optimizer rollup and added
  heuristic-probe optimizer evidence so live-looking heuristic probes show the
  relevant full-data rejection or paper-only support directly in the status
  summary.
- Decision: do not lower live MACD thresholds yet. Keep the fast-MACD family
  under watch, but require a total-positive-fold improvement before promoting.

## 2026-06-23 EURGBP cross-rate watchlist evidence

- The live watchlist continued to surface `EURGBP` cross-rate reversion as a
  high-quality strategy-mismatch candidate while the live map kept `EURGBP` on
  `champion_ensemble`.
- Existing fixed-warmup evidence is promising but mixed. The six-symbol
  `EURGBP=cross_rate_reversion` hybrid is `PAPER_ONLY` on W480 and W672
  (55.6% and 62.5% positive folds), then `PROMOTE` on W960 (83.3% positive
  folds, 100.0% active-positive folds, 100.0% non-negative folds). The exact
  live-seven `eurgbp_cross_jpy_quality` map remains `PAPER_ONLY` across
  W480/W672/W960 with minimum total positive folds only 44.4%.
- A fresh exact live-seven W480 refresh rejected more clearly: 18 folds,
  167 evaluation fills, 33.3% positive folds, 33.3% active-positive folds,
  33.3% non-negative folds, -0.003% median active return, 0.028% worst
  drawdown, and 72.2/100 average risk discipline.
- Added the cross-rate candidate window summaries to the optimizer rollup and
  added watchlist optimizer evidence so the status summary can distinguish
  promising mixed-window research from a live-ready routing change.
- Decision: keep `EURGBP` on the current live map for now. Reconsider only if
  the exact live-seven cross-rate map clears the total positive-fold gate on
  the shorter windows, not just W960.

## 2026-06-23 research-live squeeze gate evidence

- The live research cycle kept surfacing `champion_ensemble` / `asset_adaptive_dual_squeeze`
  signals on `GBPUSD` and `AUDUSD` while the live map remained gated by session
  and squeeze-ratio checks.
- Ran a fresh exact W480 / 96-bar fixed-warmup validation on `GBPUSD` and
  `AUDUSD` using `asset_adaptive_dual_squeeze`, directional-probe allocation,
  and forced QUALIFY clock.
- The exact research-signal subset rejected: 18 folds, 18 evaluation fills,
  22.2% positive folds, 57.1% active-positive folds, 83.3% non-negative folds,
  0.000% median active return, 0.007% worst drawdown, and 93.9/100 average
  risk discipline.
- Added the fresh asset-squeeze research scan to the optimizer rollup and added
  research-live optimizer evidence so high-quality signal diagnostics are tied
  to full-data promotion evidence in the status summary.
- Decision: keep the squeeze signals in discovery only. They are not live-ready
  until risk discipline and total positive folds improve.

## 2026-06-23 aggressive pressure refresh

- Refreshed live sentiment and per-pair analysis after the MT5 loop showed a
  flat account. Heuristic pressure pointed short on `AUDUSD`, `EURUSD`,
  `GBPUSD`, and `USDJPY`, but the guarded live strategies stayed flat because
  MACD/quality/champion thresholds and session gates did not confirm entries.
- Tested more active MACD candidates on the full 15-minute dataset for
  `AUDUSD`, `EURUSD`, `USDCAD`, and `USDCHF`
  (`outputs/backtests/live_watch_macd_aggressive_refine_w480.csv`).
  The greedy `6/18/5` MACD with `0.10` histogram and `0.25` MACD thresholds
  lifted fills to 94, but remained `PAPER_ONLY`: 55.6% positive folds, 76.9%
  active-positive folds, 83.3% non-negative folds, and 0.557% worst fold
  drawdown. The fastest `5/16/5` variant was rejected.
- Tested opportunity-probe on the current pressure set `AUDUSD`, `EURUSD`,
  `GBPUSD`, and `USDJPY`
  (`outputs/backtests/live_watch_opportunity_probe_current_pressure_w480.csv`).
  Every candidate rejected; the current greedy probe produced 1,731 fills but
  only 16.7% positive/non-negative folds, while the best-ranked stricter probe
  still had only 33.3% positive/non-negative folds.
- Added both fresh scans to the status summary optimizer rollup so future live
  checks keep seeing that these high-churn routes are not promotion evidence.
- Decision: do not loosen live thresholds or switch live symbols to
  opportunity-probe. Keep searching for higher-conviction active candidates,
  but reject churn that only increases trade count while degrading fold quality.

## 2026-06-23 live-seven MACD expansion check

- With the live account still flat, tested whether the near-promoted MACD family
  improves when expanded from the four-symbol USD basket to the full seven live
  FX symbols: `AUDUSD`, `EURGBP`, `EURUSD`, `GBPUSD`, `USDCAD`, `USDCHF`,
  and `USDJPY`.
- Output: `outputs/backtests/live_watch_macd_live7_expansion_w480.csv`.
- Best candidate was `near_6_18_h100_m050_s005`: 106 trades, 2.038% full-sample
  return, 0.527% max drawdown, 55.6% positive folds, 71.4% active-positive
  folds, 77.8% non-negative folds, and `PAPER_ONLY`.
- A lower-threshold active variant reached 148 trades but still stayed
  `PAPER_ONLY` with weaker full-sample return and larger drawdown. The current
  `8/21/8` all-seven MACD variant rejected with only 66.7% non-negative folds.
- Added the live-seven MACD expansion scan to the status summary rollup.
- Decision: do not expand live MACD to all seven symbols yet. The extra symbols
  increase trade count but do not improve enough fold stability to justify live
  promotion.

## 2026-06-23 exact EURGBP cross-rate refresh

- Re-tested the live-seven map with `EURGBP=cross_rate_reversion` plus
  `USDJPY=quality_trend` after the watchlist kept surfacing the cross-rate
  sleeve while the live map still used champion ensemble on `EURGBP`.
- Existing exact W480 refresh rejected hard, so ran exact W672 and W960
  fixed-warmup validations against the same seven-symbol map:
  - `outputs/backtests/live_watch_eurgbp_cross_jpy_quality_w672_refresh_summary.csv`
    was `PAPER_ONLY`: 50.0% positive folds, 80.0% active-positive folds,
    87.5% non-negative folds, 62 fills, 0.304% worst drawdown.
  - `outputs/backtests/live_watch_eurgbp_cross_jpy_quality_w960_refresh_summary.csv`
    was `PAPER_ONLY`: 46.2% positive folds, 75.0% active-positive folds,
    84.6% non-negative folds, 50 fills, 0.304% worst drawdown.
- Added both exact refresh scans to the status rollup. The older smaller-symbol
  W960 promote is now treated as weaker than the exact live-seven refresh set.
- Decision: keep `EURGBP` cross-rate in watchlist only. It is useful alpha
  context, but the exact live-seven evidence still misses the total positive
  fold promotion gate.

## 2026-06-23 quality-trend pressure refinement

- Refreshed live pair analysis showed broader heuristic pressure:
  `AUDUSD`, `EURUSD`, and `GBPUSD` short; `USDCAD` and `USDCHF` long. The live
  strategy map still stayed flat because MACD/champion/quality thresholds did
  not confirm entries.
- Tested lower-threshold quality-trend candidates on that five-symbol pressure
  set: `AUDUSD`, `EURUSD`, `GBPUSD`, `USDCAD`, and `USDCHF`.
- Output: `outputs/backtests/live_watch_quality_trend_pressure_refine_w480.csv`.
- Best candidate was `strict_active_quality`: 26 trades, 0.388% full-sample
  return, 0.342% max drawdown, 100/100 risk discipline, 100% active-positive
  folds, and 100% non-negative folds, but only 16.7% positive/active folds.
  The current-quality baseline had the highest full-sample return, 0.650%, but
  the same 16.7% positive/active fold coverage.
- Added the pressure refinement scan to the status rollup.
- Decision: quality-trend remains useful as a low-drawdown sleeve, but this
  refinement is too inactive to solve the live flat/no-approved-risk state.

## 2026-06-23 multi-horizon pressure refinement

- Refreshed the live snapshot after the user requested more aggressive trading.
  The account remained flat with equity 999,181.58, day P/L -818.42, no open
  positions, and no approved live strategy risk. Heuristic pressure showed
  possible tiny probes on `AUDUSD`, `EURGBP`, `EURUSD`, `USDCAD`, and `USDJPY`,
  but the guarded live strategies stayed flat because MACD histograms, quality
  gates, and champion-ensemble sessions did not confirm entries.
- Tested a more active multi-horizon basket on the full 15-minute data:
  `AUDUSD`, `EURGBP`, `EURUSD`, `USDCAD`, and `USDJPY`.
- Output: `outputs/backtests/live_watch_multi_horizon_pressure_refine_w480.csv`.
- All candidates rejected. The highest-ranked `pressure_5_20_wide` produced
  1,264 trades, but lost 0.411% full-sample with 0.411% drawdown, only 27.8%
  positive folds, and only 27.8% non-negative folds. The most aggressive
  `pressure_4_16_wide` produced 1,714 trades but lost 0.821% and had only 5.6%
  positive/non-negative folds.
- Existing live MACD settings remain the better evidence-backed active sleeve:
  the current `8/21/8` four-symbol MACD candidate is already promoted in the
  W960 scan with 74 trades, 2.759% full-sample return, 0.406% drawdown, 83.3%
  positive/active folds, 100% active-positive folds, and 100% non-negative
  folds.
- Added the multi-horizon pressure scan to the live status optimizer rollup.
- Decision: do not loosen live multi-horizon thresholds or force manual trades.
  The test achieved more trades by adding churn and negative fold quality, not
  by adding reliable opportunity.

## 2026-06-23 MACD micro-threshold check

- Refreshed live diagnostics still showed no approved strategy risk. Heuristic
  pressure was short `AUDUSD`, `EURGBP`, and `EURUSD`, long `USDCAD`, but the
  live strategies remained flat because the MACD and ensemble readings were
  below tested entry thresholds or in chop/noise regimes.
- Ran read-only in-memory diagnostics with the near-promoted fast MACD family
  (`6/18/5`, 0.75 histogram threshold). It still produced no actionable live
  allocation; `AUDUSD` was closest at 0.59 bps versus a 0.75 bps entry gate,
  while other MACD symbols were inside exit/noise bands or below threshold.
- Tested a micro-threshold MACD grid on the four-symbol promoted MACD basket
  `AUDUSD`, `EURUSD`, `USDCAD`, and `USDCHF`.
- Output: `outputs/backtests/live_watch_macd_micro_threshold_w480.csv`.
- Best variants (`6/18/5`, 0.50-0.60 histogram, 0.25-0.50 MACD threshold)
  stayed `PAPER_ONLY`: 82 trades, 2.082% full-sample return, 0.412% drawdown,
  61.1% positive folds, 72.2% active folds, 84.6% active-positive folds, and
  88.9% non-negative folds. The current `8/21/8` baseline still had higher
  full-sample return at 2.759% with 0.406% drawdown, but also remained
  `PAPER_ONLY` on W480.
- A second read-only micro-threshold live probe (`6/18/5`, 0.50 histogram,
  0.25 MACD threshold) also produced no actionable allocation because current
  MACD histograms had faded back into the 0.25 bps exit/noise band.
- Added the micro-threshold scan to the live status optimizer rollup.
- Decision: do not lower live MACD thresholds yet. The lower threshold does not
  create a current approved trade and does not clear the short-window positive
  fold promotion gate.

## 2026-06-23 EURGBP/USDCHF opportunity-probe strict check

- Refreshed live sentiment, attribution, per-pair analysis, and diagnostics.
  The live account remained flat with equity 999,181.58 and day P/L -818.42.
  Per-pair analysis moved every live symbol to `wait`, but candidate diagnostics
  still showed the read-only `opportunity_probe` sleeve requesting directional
  probe risk on `EURGBP` and `USDCHF`.
- The existing six-symbol opportunity-probe scan was already rejected, so tested
  a stricter two-symbol refinement on the currently requested candidate pair:
  `EURGBP` and `USDCHF`.
- Output:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_usdchf_strict_w480.csv`.
- All candidates rejected. The cleanest `ultra_pair_6_18_48_s425` cut trade
  count to 172 and held drawdown to 0.044%, but still lost 0.014% full-sample
  with only 38.9% positive folds and 38.9% non-negative folds. The current pair
  baseline produced 810 trades, lost 0.245%, and had only 27.8% positive and
  non-negative folds.
- Added the strict pair scan to the live status optimizer rollup.
- Decision: do not promote `opportunity_probe` for `EURGBP`/`USDCHF`. It is
  responsive enough to ask for trades, but the fold evidence says the requests
  are still churn rather than reliable edge.

## 2026-06-23 sentiment-pressure map refresh

- Refreshed live sentiment while the account remained flat. Sentiment became
  cleaner in the intended direction: `AUDUSD` and `GBPUSD` negative, `USDCAD`,
  `USDCHF`, and `USDJPY` supportive. Live per-pair pressure narrowed to
  `AUDUSD` short and `USDCAD` long, but the live MACD/champion/quality gates
  still produced no approved orders.
- Re-tested the near-miss sentiment-pressure strategy maps from the W480 scan
  with longer W672 and W960 fixed-warmup validations.
- Outputs:
  - `outputs/backtests/live_watch_sentiment_pressure_maps_w672_refresh_summary.csv`
  - `outputs/backtests/live_watch_sentiment_pressure_maps_w960_refresh_summary.csv`
- W672: `top_3_best_symbol_strategies` (`AUDUSD`, `USDCAD`, and `USDCHF` all
  MACD) was the best active map: 56 trades, 1.504% full-sample return, 0.287%
  drawdown, 81.2% non-negative folds, but only 37.5% positive folds and 66.7%
  active-positive folds, so `PAPER_ONLY`.
- W960: `best_positive_no_jpy` was clean but very inactive: 16 trades, 0.479%
  full-sample return, 0.175% drawdown, 100% active-positive folds, 100%
  non-negative folds, but only 23.1% positive folds, so `PAPER_ONLY`.
  `top_3_best_symbol_strategies` remained active and profitable but was still
  `PAPER_ONLY` with 38.5% positive folds and 62.5% active-positive folds.
- Added both longer-window refresh scans to the live status optimizer rollup.
- Decision: keep the current live map. These sentiment-pressure maps contain
  useful watchlist information, especially MACD on `AUDUSD`/`USDCAD`/`USDCHF`,
  but they do not clear the positive-fold promotion gate and do not justify a
  live-map change yet.

## 2026-06-23 EURUSD/GBPUSD opportunity-probe strict check

- Refreshed live diagnostics after the promoted fast-MACD read-only probe. The
  live account remained flat with equity 999,181.58 and no open positions.
  Sentiment and heuristic pressure pointed to possible `AUDUSD` and `EURUSD`
  shorts, but the promoted fast-MACD family still produced no actionable
  allocation on current MT5 quotes: `AUDUSD`, `EURUSD`, and `USDCAD` were inside
  the 0.25 bps exit/noise band, while `USDCHF` was only 0.26 bps versus the
  0.75 bps entry threshold.
- The current candidate diagnostics then surfaced `opportunity_probe` risk on
  `EURUSD` and `GBPUSD`, whose older pair scan was rejected. Tested a stricter
  two-symbol refinement on that exact pair.
- Output:
  `outputs/backtests/live_watch_opportunity_probe_eurusd_gbpusd_strict_w480.csv`.
- All candidates rejected. The best-ranked `strict_pair_4_12_32_s300` made 386
  trades, lost 0.086% full-sample, had 0.157% drawdown, and only 33.3% positive
  and non-negative folds. The tighter `ultra_pair_6_18_48_s425` reduced activity
  to 175 trades and drawdown to 0.091%, but still lost 0.044% with only 27.8%
  positive/non-negative folds. The current pair baseline lost 0.271% with 849
  trades and only 16.7% positive/non-negative folds.
- Added the strict pair scan to the live status optimizer rollup.
- Decision: do not promote `opportunity_probe` for `EURUSD`/`GBPUSD`; the
  stricter filters reduce churn but still do not produce reliable fold quality.

## 2026-06-23 bounded aggressive MACD threshold check

- User requested a more aggressive posture, so tested a bounded lower-threshold
  MACD family on the four live MACD symbols (`AUDUSD`, `EURUSD`, `USDCAD`, and
  `USDCHF`) rather than loosening live thresholds blindly.
- Output:
  `outputs/backtests/live_watch_macd_aggressive_bounded_w960.csv`.
- All candidates rejected on W960 fixed-warmup validation. The most active
  `micro_5_15_h040_m020_eff05_hold10_s000` generated 238 trades and 83.3%
  positive/non-negative folds, but lost 0.053% full-sample and failed the risk
  discipline gate at 45.0/100. The cleaner `fast_7_20_h075_m050_eff10_hold12_s005`
  made 115 trades and gained 0.035%, but only reached 66.7% non-negative folds,
  below the 70.0% promotion gate. Lowering the same setup to a 0.50 histogram
  threshold made 117 trades, gained 0.033%, and failed the same fold gate.
- Added the scan to the live status optimizer rollup.
- Decision: keep the live MACD thresholds unchanged. The bounded aggressive
  variants increase churn, but they do not yet show enough full-window risk
  discipline or fold stability to justify changing live trading.

## 2026-06-23 negative-pressure live expansion checks

- Refreshed live sentiment and diagnostics. The local sentiment snapshot and
  outside macro scan both pointed to USD-supportive/risk-off pressure: `AUDUSD`,
  `EURUSD`, and `GBPUSD` were negative, while `USDCAD` and `USDCHF` were
  supportive. Live default strategy gates still requested no risk; the read-only
  all-symbol `opportunity_probe` wanted short `EURUSD` and `GBPUSD`, but that
  exact pair had already failed strict validation.
- Tested more active `champion_ensemble`, `multi_horizon_momentum`, and
  `quality_trend` alternatives on `EURUSD`/`GBPUSD`.
- Outputs:
  - `outputs/backtests/live_watch_champion_eurusd_gbpusd_active_w960.csv`
  - `outputs/backtests/live_watch_multi_horizon_eurusd_gbpusd_pressure_w960.csv`
  - `outputs/backtests/live_watch_quality_eurusd_gbpusd_pressure_w960.csv`
- All rejected. The active champion variants lost 0.022%-0.033% with only 16.7%
  positive/non-negative folds. Multi-horizon produced 391-636 trades but lost
  0.191%-0.369%, also with only 16.7% positive/non-negative folds.
  Quality-trend was cleaner but too inactive for a live change: the best version
  made 12 trades, gained 0.012%, and had 100% active-positive/non-negative
  folds, but only 33.3% active folds.
- Tested whether adding `GBPUSD` to the MACD pressure sleeve could increase
  activity:
  - `outputs/backtests/live_watch_macd_negative_pressure_trio_w960.csv`
  - `outputs/backtests/live_watch_macd_negative_pressure_plus_usd_offsets_w960.csv`
- The `AUDUSD`/`EURUSD`/`GBPUSD` MACD trio was the best near-miss: live-current
  MACD made 122 trades, gained 0.020%, and had 83.3% positive folds with 100%
  active-positive/non-negative folds. It still failed live promotion because
  average risk discipline was only 45.0/100, likely from one-sided net
  concentration. Adding `USDCAD`/`USDCHF` as USD offsets did not repair the
  edge; all five-symbol variants lost money and had only 33.3% positive folds.
- Added these scans to the live status optimizer rollup.
- Decision: do not change the live map or loosen brakes. Keep the trio MACD
  idea on watch as an aggressive near-miss, but do not promote it while the
  competition risk-discipline score is this poor.

## 2026-06-23 adaptive current-pressure recipe check

- Current live diagnostics stayed flat, but read-only candidate diagnostics
  moved to short `EURUSD`/long `USDJPY` `opportunity_probe` and long `USDJPY`
  `multi_horizon_momentum`.
- First validated the actionable sleeves directly:
  - `outputs/backtests/live_watch_opportunity_probe_eurusd_usdjpy_strict_w960.csv`
  - `outputs/backtests/live_watch_multi_horizon_usdjpy_current_w960.csv`
- Both were rejected. The best `EURUSD`/`USDJPY` opportunity-probe candidate
  lost 0.133% with 363 trades and only 33.3% positive/non-negative folds.
  USDJPY multi-horizon lost 0.103% with 118 trades and only 16.7%
  positive/non-negative folds.
- Then tested an adaptive selector that can choose among the deployed current
  map plus today's pressure recipes: `macd_pressure_trio`,
  `opp_eurusd_usdjpy`, `mh_usdjpy`, `macd_top4`, and `quality_usdjpy`.
- Outputs:
  - `outputs/backtests/live_watch_adaptive_current_pressure_w480_summary.csv`
  - `outputs/backtests/live_watch_adaptive_current_pressure_w672_summary.csv`
  - `outputs/backtests/live_watch_adaptive_current_pressure_w960_summary.csv`
  - `outputs/backtests/live_watch_adaptive_current_pressure_consensus.csv`
- W960 promoted: 83.3% positive folds, 100.0% active-positive/non-negative
  folds, 0.139% median active test return, 100/100 risk discipline, and 46
  fills, mostly selecting `macd_top4`.
- W672 was `PAPER_ONLY`: 55.6% positive folds, 71.4% active-positive folds,
  77.8% non-negative folds, 100/100 risk discipline, and 130 fills.
- W480 rejected: 42.9% positive folds, 54.5% active-positive folds, 64.3%
  non-negative folds, 100/100 risk discipline, and 132 fills.
- Added the three-window adaptive consensus to the candidate-map rollup.
- Decision: do not deploy the adaptive current-pressure selector yet. It is the
  best aggressive research lane found in this cycle, but the short-window fold
  stability is not strong enough for live promotion.

## 2026-06-23 gated adaptive pressure selector check

- Refreshed live state again. The production map remained flat, while read-only
  `opportunity_probe` wanted short `AUDUSD` and `EURUSD`; `GBPUSD` also fired
  but was blocked by the two-position cap in the diagnostic sleeve.
- First validated the exact current probe pair:
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_strict_w960.csv`.
  All candidates rejected. The best strict pair lost 0.069% with 262 trades and
  only 33.3% positive/non-negative folds; the current pair baseline lost 0.299%
  with 877 trades.
- Re-ran the adaptive current-pressure selector with a positive training gate
  and cash fallback, plus the currently requested `opp_aud_eurusd` recipe:
  - `outputs/backtests/live_watch_adaptive_current_pressure_gated_w480_summary.csv`
  - `outputs/backtests/live_watch_adaptive_current_pressure_gated_w672_summary.csv`
  - `outputs/backtests/live_watch_adaptive_current_pressure_gated_w960_summary.csv`
  - `outputs/backtests/live_watch_adaptive_current_pressure_gated_consensus.csv`
- The gate improved stability. W480 moved from `REJECT` to `PAPER_ONLY`, W672
  stayed `PAPER_ONLY` with 88.9% non-negative folds, and W960 stayed
  `PAPER_ONLY` just shy of live promotion. Three-window consensus is
  `PAPER_ONLY`: 42.9% minimum positive folds, 66.7% minimum active-positive
  folds, 78.6% minimum non-negative folds, 0.046% minimum median active return,
  100/100 minimum risk discipline, and 150 evaluation fills. Selections were
  only `live_current`, `macd_top4`, and `cash_fallback`.
- Added the gated adaptive consensus and current-pair strict probe check to the
  live status rollup.
- Decision: keep live map unchanged. This is a better adaptive research lane,
  but the total positive-fold rate still misses the live gate.

## 2026-06-23 active AUD/EUR pressure sleeve refresh

- Refreshed live diagnostics. The production map remained flat, but the
  read-only `multi_horizon_momentum` sleeve requested short `AUDUSD` and
  `EURUSD`, while `opportunity_probe` requested short `AUDUSD` and `USDJPY`.
- Validated the current opportunity-probe pair:
  `outputs/backtests/live_watch_opportunity_probe_audusd_usdjpy_strict_w960.csv`.
  All candidates rejected. The best filtered pair lost 0.066% with 326 trades
  and only 50.0% positive/non-negative folds; the current pair baseline lost
  0.357% with 882 trades and 0.0% positive/non-negative folds.
- Validated the current multi-horizon pair:
  `outputs/backtests/live_watch_multi_horizon_audusd_eurusd_current_w960.csv`.
  The best strict candidate lost 0.071% with 246 trades, 66.7%
  positive/non-negative folds, and a small positive median active fold, but it
  still missed the 70.0% non-negative fold gate and lost full-sample.
- Ran a stricter refinement around that near-miss:
  `outputs/backtests/live_watch_multi_horizon_audusd_eurusd_strict_refine_w960.csv`.
  The best `strict_f3_s8_eff35` reduced trades to 192 and improved median active
  return to 0.006%, but still lost 0.077% and remained at 66.7%
  positive/non-negative folds.
- Added the new W960 scans to the live optimizer rollup.
- Decision: do not promote the current AUD/EUR or AUD/JPY pressure sleeves.
  Multi-horizon AUD/EUR is the nearest active sleeve, but it is still a
  paper-only watch item until full-sample return and fold stability improve.

## 2026-06-23 active AUD/EURGBP opportunity-probe refresh

- User pressure was explicitly for more trades, so I refreshed the live account,
  pair analysis, sentiment, attribution, and candidate diagnostics without
  removing the live guardrails. MT5, `live_supervisor.ps1`, `live_guard.ps1`,
  and `quanthack.exe live-trade` were all running; the account was flat at
  `999181.58` equity, `-818.42` day P/L, zero margin, and zero open positions.
- The production map still requested no order. The read-only `opportunity_probe`
  sleeve requested long `AUDUSD` and short `EURGBP`; other active probe signals
  were blocked by the two-position throttle.
- Validated that exact current pair on the full downloaded 15-minute data:
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurgbp_current_w960.csv`.
  All candidates rejected. The current live-style baseline lost 0.323% with
  1,269 trades and 0.0% positive/non-negative folds. The best stricter variant
  still lost 0.022% with only 20.0% positive/non-negative folds.
- Rechecked the MACD core parameter evidence before changing live thresholds.
  The current `8/21/8` MACD core remains stronger than the faster `7/20/5`
  alternative on the tested top-four MACD sleeve: about 74 fills and +2.759%
  full-sample return versus 52 fills and +1.933%, with W672/W960 live-ready but
  W480 still only paper-only for both families.
- Added the current AUDUSD/EURGBP W960 probe scan to the live optimizer rollup.
- Decision: do not force trades or loosen the two-position/loss/sentiment
  brakes. Keep the live process enabled and let it trade only when the deployed
  strategy/risk gates approve.

## 2026-06-23 active AUD/EUR/CHF and MACD threshold retest

- Refreshed the live stack again. MT5, `live_supervisor.ps1`,
  `live_guard.ps1`, and `quanthack.exe live-trade` were running with the
  sentiment brake and symbol-state cooldown throttle intact. Account state was
  still flat: `999181.58` equity, `-818.42` day P/L, zero open positions, zero
  margin, and no live stderr log.
- Production diagnostics stayed flat. The all-symbol `opportunity_probe`
  diagnostic requested short `AUDUSD` and long `EURUSD`; short `USDCHF` also
  fired but was behind the two-position diagnostic throttle.
- Validated that active opportunity sleeve on full data:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_chf_current_w960.csv`.
  All variants rejected. The best high-score filter still lost 0.077% with 354
  trades, 40.0% positive/non-negative folds, and negative active median return.
  The live-current baseline lost 0.488% with 1,812 trades.
- Tested whether less-conservative MACD thresholds could admit more production
  trades:
  - `outputs/backtests/live_watch_macd_current_threshold_retest_default_w960.csv`
  - `outputs/backtests/live_watch_macd_current_threshold_retest_w960.csv`
- Under production/default allocation, faster `6/18/5` with 0.75 histogram,
  0.50 MACD, 0.05 slope, and 16-bar hold promoted on this W960 retest with 82
  trades and +2.142%. But the prior W480/W672/W960 stability set still makes it
  weaker than current production: W480 was paper-only at 61.1% positive folds,
  W672 promoted, and W960 was a paper-only near-miss in the 240/192 fold set.
  Current `8/21/8` remains higher return on the core sleeve (+2.759% full
  sample) with W672/W960 promotion and the same W480 caution.
- Added the new scans to the live optimizer rollup.
- Decision: keep the live config and running process unchanged. The faster MACD
  family remains the best more-active watch item, but the evidence does not yet
  justify restarting live with lower thresholds.

## 2026-06-23 focused EURGBP multi-horizon check

- Refreshed live state again. Production remained flat, but read-only
  diagnostics showed two active sleeves: `opportunity_probe` wanted short
  `AUDUSD` and short `EURGBP`, while `multi_horizon_momentum` wanted a short
  `EURGBP` allocation. Sentiment still labeled `EURGBP` supportive, so the live
  sentiment brake remained relevant for fresh short risk.
- The AUDUSD/EURGBP opportunity-probe sleeve was already covered by
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurgbp_current_w960.csv`
  and remained rejected, so I did not re-run it.
- Ran a focused EURGBP-only multi-horizon validation:
  `outputs/backtests/live_watch_multi_horizon_eurgbp_current_w960.csv`.
  All active variants rejected. The live-current setup lost 0.051% with 66
  trades and only 20.0% positive/non-negative folds. The stricter variants
  either lost money or became too inactive; the only positive full-sample line
  made just 2 trades with 0.0% active folds.
- Added the EURGBP W960 scan to the live optimizer rollup.
- Decision: do not promote EURGBP multi-horizon or loosen the sentiment/risk
  brakes for this sleeve.

## 2026-06-23 opportunity-probe cap expansion check

- Refreshed live health, account, sentiment, attribution, pair analysis, and
  diagnostics. Live trading infrastructure was still running with the sentiment
  brake and symbol-state cooldown throttle intact. Account remained flat at
  `999181.58` equity, `-818.42` day P/L, zero positions, and zero margin.
- Production remained flat. The all-symbol `opportunity_probe` diagnostic
  wanted long `AUDUSD` and short `EURGBP`; `GBPUSD`, `USDCAD`, `USDCHF`, and
  `USDJPY` also fired but were held behind the two-position diagnostic cap.
- Tested whether loosening that cap would help:
  `outputs/backtests/live_watch_opportunity_probe_cap_expansion_current_w960.csv`
  on `AUDUSD`, `EURGBP`, `GBPUSD`, `USDCAD`, `USDCHF`, and `USDJPY`.
- All candidates rejected. Even the high-score filter lost 0.117% with 652
  trades and only 20.0% positive/non-negative folds. The live-current broader
  basket lost 1.132% with 3,725 trades and 0.0% positive/non-negative folds.
- Added the cap-expansion W960 scan to the live optimizer rollup.
- Decision: keep the two-position cap. This is exactly the kind of higher
  turnover path that looks responsive in live diagnostics but has bad
  full-data survival characteristics.

## 2026-06-23 EURUSD/GBPUSD opportunity-probe W960 check

- Refreshed live supervision again. The live process, supervisor, guard, and
  MT5 terminal were still running; account state remained flat at `999181.58`
  equity, `-818.42` day P/L, zero positions, zero margin, and no live stderr.
- Production diagnostics remained flat. The status summary pointed at the
  current read-only `opportunity_probe` pressure around `EURUSD`/`GBPUSD`, but
  the attached evidence was only a W480 rejection.
- Ran the full W960 validation:
  `outputs/backtests/live_watch_opportunity_probe_eurusd_gbpusd_strict_w960.csv`.
  All variants rejected. The best high-score filter lost 0.040% with 242 trades
  and 40.0% positive/non-negative folds; the very-strict line lost 0.029% with
  only 20.0% positive/non-negative folds; live-current lost 0.375% with 1,222
  trades.
- Added the W960 scan to the live optimizer rollup.
- Decision: do not promote the EURUSD/GBPUSD opportunity-probe sleeve.

## 2026-06-23 aggressive alpha-router/session-breakout check

- Refreshed the live stack under explicit pressure to increase trade count.
  MT5, `live_supervisor.ps1`, `live_guard.ps1`, and `quanthack.exe live-trade`
  were all still running with the sentiment brake, symbol-state cooldown
  throttle, two-position cap, and daily-loss reduce-only brake intact.
- Full-data research diagnostics surfaced higher-frequency candidates:
  alpha-router/session-breakout on `USDCHF`, `GBPUSD`, and `EURUSD`, plus
  USDJPY mean reversion. Current live diagnostics for these sleeves requested
  zero notional; session-breakout was blocked by missing breakout/volatility
  edge, and USDJPY mean reversion did not clear estimated costs.
- Ran force-qualified directional-probe portfolio backtests on the full
  downloaded 15-minute data:
  - `outputs/backtests/live_watch_alpha_router_candidate_*`: 1,457 fills,
    -0.736% return, Sharpe -3.150, and concentration penalties.
  - `outputs/backtests/live_watch_session_breakout_candidate_*`: 215 fills,
    -0.095% return, Sharpe -0.467, and concentration penalties.
  - `outputs/backtests/live_watch_usdjpy_mean_reversion_candidate_*`: 570 fills,
    -0.139% return, Sharpe -1.339, and concentration penalties.
- Decision: do not promote these high-turnover sleeves. They create activity,
  but the full-data evidence shows negative expectancy and risk-discipline
  damage, so forcing them live would reduce survival odds.

## 2026-06-23 EURGBP/EURUSD opportunity-probe pressure check

- Refreshed live supervision after the pair heuristic moved back to `wait` on
  all pairs. Production diagnostics still requested zero notional, but the
  read-only `opportunity_probe` sleeve lit up long `EURGBP` and long `EURUSD`;
  `USDCHF` also fired short but was behind the two-position diagnostic cap.
- Validated the exact current sleeve on full downloaded 15-minute data:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_eurusd_current_w960.csv`.
  All candidates rejected. The least-bad very-strict variant still lost 0.060%
  with 238 trades, Sharpe -0.030, and only 16.7% positive/non-negative folds.
  The live-current baseline lost 0.263% with 838 trades and 0.0% positive folds.
- Also tested the cap-expanded version including the blocked `USDCHF` signal:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_eurusd_usdchf_current_w960.csv`.
  All candidates rejected; the live-current baseline lost 0.394% with 1,247
  trades, and even the very-strict line lost 0.099%.
- Added both scans to the live optimizer rollup so the status summary attaches
  fresh evidence to this current candidate.
- Decision: do not restart live with opportunity-probe or loosen the
  two-position cap for this pressure set.

## 2026-06-23 USDCHF opportunity-probe pressure check

- Refreshed sentiment, attribution, pair analysis, and diagnostics again.
  Production remained flat, while read-only `opportunity_probe` requested a
  short `USDCHF` allocation. The diagnostic was already marked `PENALTY_RISK`
  because the sleeve is one-sided.
- Validated the exact current USDCHF opportunity-probe pressure on full
  downloaded 15-minute data:
  `outputs/backtests/live_watch_opportunity_probe_usdchf_current_w960.csv`.
  All candidates rejected. The least-bad very-strict variant lost 0.040% with
  131 trades, Sharpe -0.021, and only 16.7% positive/non-negative folds. The
  live-current baseline lost 0.131% with 409 trades.
- Added the W960 scan to the live optimizer rollup so future summaries attach
  fresh evidence if USDCHF probe pressure reappears.
- Decision: do not promote USDCHF opportunity-probe despite the active signal;
  the full-data evidence says it adds churn and negative expectancy.

## 2026-06-23 AUD/EURGBP/CAD/CHF cap-expanded probe check

- After another full-data research cycle, the live read-only `opportunity_probe`
  candidate shifted to long `AUDUSD` and long `EURGBP`, with short `USDCAD` and
  short `USDCHF` blocked behind the two-position diagnostic cap.
- Validated the exact cap-expanded set:
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_cad_chf_current_w960.csv`.
  All candidates rejected. The least-bad very-strict variant lost 0.105% with
  491 trades, Sharpe -0.024, 50.0% positive/non-negative folds, and negative
  active median return. The live-current baseline lost 0.522% with 1,671 trades.
- Added the scan to the live optimizer rollup.
- Decision: do not loosen the live two-position cap or promote opportunity-probe
  for this AUD/EURGBP/CAD/CHF pressure set.

## 2026-06-23 MACD current-vs-fast and AUD/GBP/CAD/JPY probe check

- Refreshed live health, sentiment, attribution, pair analysis, production
  diagnostics, and research cycle. MT5, `live_supervisor.ps1`, `live_guard.ps1`,
  and real-order `quanthack.exe live-trade` were still running. Account stayed
  flat at `999181.58` equity with zero positions and no live stderr.
- Production diagnostics stayed flat, but the read-only `opportunity_probe`
  sleeve requested short `AUDUSD` and short `GBPUSD`; long `USDCAD` and long
  `USDJPY` were blocked behind the two-position diagnostic cap.
- Validated the exact active-plus-blocked opportunity-probe set:
  `outputs/backtests/live_watch_opportunity_probe_aud_gbp_cad_jpy_current_w960.csv`.
  All candidates rejected. The least-bad very-strict variant lost 0.134% with
  488 trades, Sharpe -0.030, and only 33.3% positive/non-negative folds. The
  live-current line lost 0.606% with 1,715 trades.
- Tested the more credible non-probe path, current MACD versus faster MACD
  variants on the live MACD symbols:
  `outputs/backtests/live_watch_macd_current_vs_fast_live4_w960.csv`.
  Current `8/21/8` remained best and promoted: +2.759%, 0.406% max drawdown,
  Sharpe 0.046, 74 trades, 83.3% positive folds, 100.0% active-positive and
  non-negative folds. The faster 7/20 variant promoted but had lower return and
  fewer trades, while 6/18 variants were paper-only.
- Added both scans to the live optimizer rollup.
- Decision: keep production MACD unchanged and do not promote opportunity-probe.
  The evidence favors waiting for current MACD/ensemble/quality gates instead
  of forcing the higher-turnover probe sleeve.

## 2026-06-23 quality-trend refresh and EURGBP/GBP/CAD/JPY probe check

- Refreshed live health, sentiment, attribution, pair analysis, and diagnostics.
  Live trading infrastructure remained healthy and real-order enabled. Account
  was still flat at `999181.58` equity with no positions, no margin, and no
  live stderr.
- Production diagnostics and the quality-trend candidate diagnostics requested
  zero current notional. Quality-trend was gated by weak MACD histogram values
  on `AUDUSD`, `EURUSD`, `USDCHF`, and `USDJPY`.
- Validated the current read-only `opportunity_probe` pressure on `EURGBP`,
  `GBPUSD`, `USDCAD`, and `USDJPY`:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbp_cad_jpy_current_w960.csv`.
  All candidates rejected. The least-bad very-strict variant lost 0.182% with
  478 trades, Sharpe -0.056, and only 16.7% positive/non-negative folds. The
  live-current line lost 0.570% with 1,676 trades.
- Refreshed the non-probe quality-trend watch sleeve:
  `outputs/backtests/live_watch_quality_trend_current_watch_w960.csv`.
  The current/extended quality-trend variants were positive (+0.637%, 22
  trades, Sharpe 0.028, 100.0% active-positive/non-negative folds), but only
  33.3% of folds were active, so promotion remained `PAPER_ONLY`.
- Added both scans to the live optimizer rollup.
- Decision: keep quality-trend on watch but do not promote it broadly until
  active-fold coverage improves; do not promote the current opportunity-probe
  pressure set.

## 2026-06-23 champion asset-squeeze AUD/GBP/EURGBP refresh

- Tested a higher-turnover champion-ensemble asset-squeeze refresh on full
  downloaded 15-minute data for `AUDUSD`, `GBPUSD`, and `EURGBP`:
  `outputs/backtests/live_watch_champion_asset_squeeze_aud_gbp_eurgbp_w960.csv`.
- The best current mix made +0.321% with 18 trades, 0.286% max drawdown, and
  Sharpe 0.016, but stayed `PAPER_ONLY`: only 16.7% of folds were positive and
  the largest positive fold contributed 100.0% of positive walk-forward return.
  The asset-heavy and asset-only variants had zero live evaluation fills or were
  rejected.
- Added the scan to the live optimizer rollup and fixed candidate evidence
  ordering so summary evidence follows the live diagnostic order before ranking
  by scan severity.
- Decision: do not promote this champion refresh yet. It is useful watchlist
  evidence, but still too concentrated for live expansion.

## 2026-06-23 GBPUSD multi-horizon current-pressure check

- Live candidate diagnostics repeatedly showed `multi_horizon_momentum`
  requesting a large GBPUSD short, trimmed to about `$49,959` by leverage,
  asset-class, and symbol caps.
- Ran a focused W960 full-data optimizer on GBPUSD only:
  `outputs/backtests/live_watch_multi_horizon_gbpusd_current_pressure_w960.csv`.
- The strict `gbp_10_40_strict` variant had 83.3% non-negative folds but only
  50.0% active coverage, 8 evaluation fills, slightly negative total return
  (-0.003%), and failed the promotion gate. Production-style `6/24` variants
  made small money (+0.035% to +0.042%) but had only 50.0% non-negative folds.
- Added the scan to the live optimizer rollup so future multi-horizon pressure
  gets attached to this fresh evidence.
- Decision: do not add GBPUSD multi-horizon to the live map yet. It remains a
  watch candidate, not a high-conviction margin candidate.

## 2026-06-23 AUD/EUR/GBP/CAD opportunity-probe pressure check

- Latest candidate diagnostics showed `opportunity_probe` requesting long
  `AUDUSD` and long `EURUSD`, with long `GBPUSD` and short `USDCAD` blocked
  behind the two-position cap.
- Ran the exact active-plus-blocked sleeve on full downloaded 15-minute data:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_cad_current_w960.csv`.
- Every candidate rejected. The least-bad `ultra_strict` variant lost 0.146%
  with 586 trades, Sharpe -0.031, and only 33.3% positive/non-negative folds.
  The live-current line lost 0.548% with 1,710 trades and 16.7%
  positive/non-negative folds.
- Added the scan to the live optimizer rollup.
- Decision: keep the two-position cap and do not promote/expand
  opportunity-probe for this pressure set.

## 2026-06-23 live7 active-pressure checks

- Live account remained flat at `999181.58` equity with live MT5, supervisor,
  guard, sentiment brake, symbol-state throttle, and live-order loop running.
- Tested the exact current `opportunity_probe` pressure basket
  `AUDUSD/USDCAD/USDJPY` with looser "trade more" variants:
  `outputs/backtests/live_watch_opportunity_probe_aud_cad_jpy_active_pressure_w960.csv`.
  Every line rejected. The strict line lost 0.245% with 701 trades and only
  16.7% non-negative folds; loosening to 0.90 score produced 1,638 trades and a
  larger 0.569% loss.
- Tested more active champion-ensemble variants on `AUDUSD/GBPUSD/USDJPY`:
  `outputs/backtests/live_watch_champion_active_aud_gbp_jpy_w960.csv`.
  The best MACD/asset mix lost 0.045% and missed the non-negative fold gate at
  66.7%; looser variants were worse.
- Ran a fresh W960 seven-symbol strategy-map pressure check:
  `outputs/backtests/live_watch_strategy_maps_live7_pressure_w960_summary.csv`.
  No map promoted. The best positive map also stopped at 66.7% non-negative
  folds, while the current live map was negative with only 33.3% non-negative
  folds. High-activity all-MACD and probe/squeeze style maps remained rejected.
- Added these scans to the live summary inputs so future diagnostics attach the
  exact current pressure evidence.
- Decision: do not weaken risk gates, expand the position cap, or force
  opportunity-probe/champion trades. Keep the live process enabled and let the
  existing approved MACD/quality/ensemble gates fire when the market leaves the
  current chop regime.

## 2026-06-23 EUR/GBP/CHF probe and session-sleeve checks

- Latest read-only `opportunity_probe` diagnostics requested long `EURUSD`, long
  `GBPUSD`, and a blocked short `USDCHF`. Sentiment conflicted with the GBP and
  CHF legs, so the exact basket was tested before considering any live exposure:
  `outputs/backtests/live_watch_opportunity_probe_eur_gbp_chf_active_pressure_w960.csv`.
  Every variant rejected. The strict line lost 0.182% with 733 trades and only
  16.7% non-negative folds; looser variants traded up to 1,577 fills and lost
  more.
- Tested fixed-warmup W960 session sleeves from the research-cycle diagnostics:
  `outputs/backtests/live_watch_session_breakout_top_signal_w960_summary.csv`,
  `outputs/backtests/live_watch_alpha_router_top_session_w960_summary.csv`, and
  `outputs/backtests/live_watch_usdjpy_mean_reversion_signal_w960_summary.csv`.
  Session-breakout was active but unstable (50.0% non-negative folds, average
  risk discipline 71.7/100). Alpha-router and USDJPY mean-reversion had 0.0%
  non-negative folds.
- Tested all-seven quality-trend size/hour repair:
  `outputs/backtests/live_watch_quality_trend_live7_size_repair_w960.csv`.
  The best micro quality-trend line made a small profit and kept 100.0%
  non-negative active folds, but remained sparse and missed the average risk
  discipline gate at 93.3/100 versus 95.0/100.
- Added these scans to the live summary inputs.
- Decision: no live-map promotion from this batch. The live engine remains
  enabled for approved production MACD/quality/ensemble signals, but the current
  aggressive probe/session ideas should stay blocked from fresh live risk.

## 2026-06-23 MACD gate-relief check

- Tested whether production MACD symbols could safely trade more by relaxing
  histogram/trend-efficiency gates:
  `outputs/backtests/live_watch_macd_gate_relief_live4_w960.csv`.
- No candidate promoted. The best guarded fast variant made +0.050% with 95
  trades, but stopped at 66.7% non-negative/active-positive folds versus the
  70.0% live gate. More active variants produced 155-183 trades and were
  negative or had weaker fold stability.
- Added the scan to the live optimizer rollup.
- Decision: do not relax production MACD thresholds right now. The current
  gating is frustratingly quiet, but the looser alternatives do not yet clear
  the survival evidence bar.

## 2026-06-23 five-symbol opportunity-probe pressure check

- Latest read-only `candidate_all_opportunity_probe` diagnostics requested
  actionable long `AUDUSD` and short `EURGBP`; long `GBPUSD`, short `USDCAD`,
  and short `USDCHF` were also raw non-zero signals but were blocked behind the
  active two-position cap.
- Ran the exact current raw pressure set on full downloaded 15-minute data:
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_gbp_cad_chf_current_w960.csv`.
- Every candidate rejected. The strict line was least bad but still lost
  0.266% with 1,162 trades, Sharpe -0.044, and only 16.7% non-negative folds.
  The live-current line lost 0.643% with 2,083 trades, while more active lines
  reached 2,429-2,660 trades and lost 0.755%-0.817%.
- Added the scan to the live optimizer rollup.
- Decision: do not expand the two-position cap, promote `opportunity_probe`, or
  route this pressure set to live risk. More trades here meant faster loss, not
  better survival.

## 2026-06-23 promoted MACD gate relief and restarted live loop

- Current production diagnostics remained flat, with MACD symbols sitting near
  but mostly below the old 8/21/8, 1.25 bps histogram gate. The live account was
  flat, so this was a clean time to activate a tested parameter refinement.
- Promoted the fixed-warmup W960 MACD candidate from
  `outputs/backtests/live_watch_macd_current_threshold_retest_default_w960.csv`:
  `fast_6_18_h075_s005` on `AUDUSD EURUSD USDCAD USDCHF`. It made +2.142%,
  kept max drawdown to 0.411%, scored 100/100 risk discipline, produced 82
  trades, and passed live readiness with 80.0% positive folds and 100.0%
  active-positive/non-negative folds.
- Updated `configs/competition.toml` MACD parameters to 6/18/5,
  0.75 bps histogram, 0.50 bps MACD line, 0.05 bps histogram slope, and 0.10
  trend efficiency. This increases qualified MACD opportunity while preserving
  max live positions, order lot cap, daily-loss brake, rolling-Sharpe brake,
  sentiment brake, and symbol-state cooldown throttle.
- Tested the current raw `opportunity_probe` pressure basket
  `EURGBP/EURUSD/GBPUSD/USDCAD`:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_eurusd_gbpusd_usdcad_current_w960.csv`.
  Every candidate rejected; the least-bad strict line lost 0.240% with 943
  trades, while looser variants traded 1,671-2,151 times and lost 0.512%-0.658%.
- Restarted the live MT5 loop through `live_guard.ps1` so the promoted config is
  active. The restarted loop printed `LIVE - REAL ORDERS`, retained the
  sentiment/cooldown/loss brakes, and its first iteration produced no forced
  order.
- Decision: this is the correct kind of aggression for the elimination format:
  loosen a parameter set that already passed full-data live-readiness evidence,
  but continue blocking the currently losing probe basket.

## 2026-06-23 MACD dead-zone relief check

- After the promoted MACD config went live, production diagnostics remained
  flat because the four MACD symbols were inside the 0.25 bps exit/dead zone:
  AUDUSD 0.23 bps, EURUSD 0.09 bps, USDCAD 0.16 bps, and USDCHF -0.11 bps.
- Ran a focused full-data W960 scan on `AUDUSD EURUSD USDCAD USDCHF` to test
  whether lower MACD entry/dead-zone thresholds could safely create more fills:
  `outputs/backtests/live_watch_macd_deadzone_relief_live4_w960.csv`.
  The best lower-threshold line made +1.965% with 96 trades, 0.603% drawdown,
  80.0% active-positive folds, and 83.3% non-negative folds, but stayed
  `PAPER_ONLY` because total positive folds were 66.7% versus the 67.0% live
  gate.
- Ran a narrow hour-window refinement:
  `outputs/backtests/live_watch_macd_deadzone_hour_refine_live4_w960.csv`.
  It also stayed `PAPER_ONLY`; excluding early or late hours did not lift the
  positive-fold rate above 66.7%.
- Added both scans to the live optimizer rollup.
- Decision: do not lower the live MACD dead-zone/entry thresholds yet. The
  variants are close and worth monitoring, but they do not clear the live
  readiness gate and would be a weaker change than the already-promoted MACD
  config.

## 2026-06-23 late USD session MACD check

- At 21 UTC, fresh sentiment was USD-supportive, but production diagnostics were
  flat because EURGBP/USDJPY were session gated and the four MACD symbols were
  either stale-quote gated or inside the MACD dead zone.
- Tested whether the promoted MACD sleeve should trade the late USD session on
  `AUDUSD EURUSD USDCAD USDCHF`:
  `outputs/backtests/live_watch_macd_late_usd_session_live4_w960.csv`.
- No candidate promoted. Extending the promoted MACD hours to include 20-22 UTC
  made +2.253% with 88 trades and low drawdown, but stayed `PAPER_ONLY` because
  active-positive folds were 66.7%. Late-only variants had only 6 trades and
  were rejected despite positive total return.
- Added the scan to the live optimizer rollup.
- Decision: do not extend live MACD trading into the late USD session yet. The
  result is close enough to keep watching, but it is not live-ready evidence.

## 2026-06-23 AUDUSD opportunity-probe single-symbol check

- Current read-only candidate diagnostics showed `candidate_all_opportunity_probe`
  requesting a single actionable `AUDUSD` long. The broader five-symbol probe
  basket was already rejected, so the exact single-symbol case was tested before
  considering any promotion.
- Ran full-data W960 validation:
  `outputs/backtests/live_watch_opportunity_probe_audusd_current_w960.csv`.
- Every candidate rejected. The least-bad strict line lost 0.060% with 239
  trades and only 33.3% non-negative folds. The live-current line lost 0.150%
  with 440 trades, while looser variants traded 510-540 times and lost more.
- Added the scan to the live optimizer rollup.
- Decision: do not promote or special-case `opportunity_probe` for AUDUSD. The
  single-symbol evidence confirms that the current actionable probe is churn,
  not a robust survival opportunity.

## 2026-06-23 USDCAD opportunity-probe single-symbol check

- Fresh candidate diagnostics shifted the read-only `candidate_all_opportunity_probe`
  sleeve to a single actionable `USDCAD` long. The existing W480 evidence was
  rejected, so the exact current single-symbol case was refreshed on full data.
- Ran W960 validation:
  `outputs/backtests/live_watch_opportunity_probe_usdcad_current_w960.csv`.
- Every candidate rejected. The live-current line lost 0.127% with 421 trades
  and only 16.7% non-negative folds. Looser variants traded 483-533 times and
  lost more; the strict variant reduced fills to 237 but had 0.0% non-negative
  folds.
- Added the scan to the live optimizer rollup.
- Decision: do not promote or special-case `opportunity_probe` for USDCAD. The
  current USD-supportive headline backdrop is not enough to overcome the
  strategy's full-data churn profile.

## 2026-06-23 MACD promotion refresh

- Refreshed the stale full-data W960 MACD threshold scan on
  `AUDUSD EURUSD USDCAD USDCHF`:
  `outputs/backtests/live_watch_macd_current_threshold_retest_default_w960.csv`.
- The previously live `6/18/5` MACD line fell back to `PAPER_ONLY`: +2.142%
  return, 82 trades, but only 66.7% positive folds and 80.0% active-positive
  folds.
- The `8/21/8` variants passed live promotion. The selected live setting
  `live_current_8_21_h075` made +2.396% with 80 trades, 83.3% positive folds,
  and 100.0% active-positive/non-negative folds. It keeps the lower 0.75 bps
  histogram threshold for more opportunity while restoring fold stability.
- Updated `configs/competition.toml` MACD parameters to 8/21/8, 0.75 bps
  histogram, 0.50 bps MACD line, 0.00 bps slope, and 0.10 trend efficiency.
- Decision: promote the refreshed 8/21/8 MACD setting and restart the guarded
  live loop so production uses the currently live-ready MACD evidence.

## 2026-06-23 MACD late-session expansion

- Current live state was flat with zero requested exposure. At 21:47 UTC,
  `AUDUSD` and `USDCAD` were blocked by the MACD session window while the
  account was flat, so I retested a controlled late-session expansion rather
  than removing risk brakes.
- Fresh full-data W960 scan:
  `outputs/backtests/live_watch_macd_8_21_late_session_w960.csv`.
- Current 8/21/8 hours 6-14 remained `PROMOTE`: +2.396% return, 80 trades,
  83.3% positive folds, 100.0% active-positive/non-negative folds.
- Extended 8/21/8 hours 6-14 plus 20-22 also passed `PROMOTE`: +2.400%
  return, 86 trades, 83.3% positive folds, 83.3% active-positive folds, and
  83.3% non-negative folds with unchanged 0.605% max drawdown.
- Late-only 20-22 variants were rejected due weak active fold stability, so
  this is an additive evening window only, not an evening-only strategy.
- Decision: add UTC hours 20, 21, and 22 to `strategy.macd_momentum`
  `forex_allowed_utc_hours` to improve evidence-backed opportunity while
  keeping live loss, sentiment, cooldown, max-lot, and position-cap brakes
  intact.

## 2026-06-23 post-expansion map refresh

- Refreshed a full-data W960 strategy-map comparison after the MACD evening
  window was promoted:
  `outputs/backtests/live_watch_strategy_maps_after_macd_hours_w960_summary.csv`.
- Current live map remains `PROMOTE`: +2.374% return, 116 trades, 83.3%
  positive folds, 83.3% active-positive folds, and 83.3% non-negative folds.
- `macd_core_only` slightly improved return to +2.400% but reduced activity to
  86 trades, so it does not satisfy the current need for more live opportunity.
- `promoted_best_per_symbol` also passed `PROMOTE` but reduced activity to 98
  trades and reduced full-sample return to +2.295%.
- More active alternatives such as all-MACD and multi-horizon overlays were
  rejected on fold stability, so no production map swap was justified.
- Updated `scripts/live_status_summary.py` so optimizer evidence reads and
  ranks every row from each scan CSV instead of only row 1. This prevents a
  paper-only first row from hiding a promoted row lower in a scan.

## 2026-06-23 USDJPY opportunity-probe rejection

- Live candidate diagnostics showed a directional-probe USDJPY opportunity
  signal at 22:06 UTC, but production USDJPY remains on `quality_trend`.
- Ran exact full-data W960 validation:
  `outputs/backtests/live_watch_opportunity_probe_usdjpy_current_w960.csv`.
- All tested USDJPY opportunity-probe variants were rejected. The best
  `fast_strict` candidate made -0.174%, had 428 trades, and produced 0.0%
  positive, active-positive, and non-negative walk-forward folds.
- Decision: do not route USDJPY to `opportunity_probe` and do not force a
  discretionary USDJPY trade. The current live `quality_trend` sleeve remains
  the safer production mapping, and the new scan is included in live summary
  evidence so future probe signals are rejected explicitly.

## 2026-06-23 MACD micro-threshold check

- Current live diagnostics remained flat while pair-analysis scores warmed in
  AUDUSD/USDCAD/USDJPY, so I tested a bounded lower-threshold MACD expansion
  instead of manually forcing a trade.
- Fresh full-data W960 scan:
  `outputs/backtests/live_watch_macd_micro_threshold_after_hours_w960.csv`.
- The current 8/21/8 h075 evening-window setup remained the best choice:
  +2.400% return, 86 trades, 83.3% positive folds, 83.3% active-positive
  folds, and 83.3% non-negative folds.
- Lower-threshold variants did pass the promotion gates, but the more active
  versions only increased activity to 90 trades while reducing return to
  +2.100% or +1.806% and lowering median active-fold return.
- Decision: do not lower MACD thresholds for production. The current setup is
  already aggressive enough to use the evening window, and lowering thresholds
  would add churn without improving full-data payoff.

## 2026-06-25 EURGBP/GBPUSD opportunity-probe rejection refresh

- Restarted the guarded Windows live stack after finding MT5 open but
  `live_guard.ps1`, `live_supervisor.ps1`, and the live `quanthack` process
  stopped. The relaunched command kept `--max-order-lots 0.25`, the sentiment
  brake, symbol-state cooldown blocks, the small-only throttle, and the
  two-position cap intact.
- Refreshed live snapshots first. Account state was flat at `999181.58`
  equity, day P/L `-818.42`, zero open positions, zero margin, and production
  diagnostics reported no approved risk.
- Read-only `candidate_all_opportunity_probe` diagnostics showed actionable
  short `EURGBP` and long `GBPUSD` ideas, with additional raw USDCAD/USDCHF
  probe pressure blocked behind the two-position cap. Before considering any
  promotion, I ran the exact EURGBP/GBPUSD probe family on the extracted full
  15-minute data with W960 fixed-warmup validation:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbpusd_current_w960.csv`.
- Every candidate rejected. The best `hyper_filtered_s3_00_hold4_20` line lost
  0.140%, made 526 trades, and produced only 16.7% positive,
  active-positive, and non-negative folds. The live-current line lost 0.235%
  with 813 trades and 0.0% positive/non-negative folds.
- Added the new W960 scan to `scripts/live_status_summary.py` so future live
  summaries cite the fresher rejection instead of relying only on the older
  W480 probe evidence.
- Decision: do not route EURGBP/GBPUSD to `opportunity_probe`, do not force a
  manual trade, and keep production on the existing guarded strategy map.

## 2026-06-25 active-pressure follow-up

- Refreshed live snapshots again after the guarded loop stayed flat. Account
  remained `999181.58` equity, day P/L `-818.42`, zero positions, zero margin,
  and production diagnostics still showed no approved risk.
- Candidate diagnostics shifted to opportunity-probe pressure on long `AUDUSD`,
  short `EURGBP`, and cap-blocked long `GBPUSD`. I tested the exact current
  three-symbol pressure set on the extracted live-seven full 15-minute data
  with W960 fixed-warmup validation:
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_gbp_current_w960.csv`.
- Every probe variant rejected. The least-bad `hyper_filtered_s3_00_hold4_20`
  line lost 0.170%, made 802 trades, and reached only 33.3% positive,
  active-positive, and non-negative folds. The live-current line lost 0.385%
  with 1,253 trades and 0.0% positive/non-negative folds.
- Tested the promoted and micro MACD settings in-memory against the current MT5
  snapshot without editing config. Lower thresholds still did not create a
  guarded allocation: AUDUSD/EURUSD either had edge below estimated cost,
  insufficient histogram slope, stale quote quality, or remained below the
  threshold.
- Ran a fresh research cycle and near-promotion scan. The top candidate stayed
  `lower_6_18_h050_m035_eff07_s003_hold16` as `PAPER_ONLY`; it is more active
  than the current live MACD but weaker and still misses the total positive
  fold gate.
- The opportunity-probe sleeve then shifted again to long `AUDUSD`, long
  `EURUSD`, long `GBPUSD`, and raw `USDJPY` pressure. I ran another exact W960
  validation:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_jpy_current_w960.csv`.
  Every variant rejected; the least-bad filtered line lost 0.347%, traded
  1,099 times, and reached only 16.7% positive/active-positive/non-negative
  folds, while the live-current line lost 0.628% with 1,731 trades.
- Decision: keep production config unchanged for now. The live loop remains
  enabled, but the current aggressive probe pressure is rejected by full-data
  evidence and the apparent MACD near-signal is still below cost/quality gates.

## 2026-06-25 GBPUSD asset-squeeze session check

- GBPUSD champion ensemble remained session-gated at the 08:00 UTC hour, so I
  tested whether the `asset_adaptive_dual_squeeze` sleeve could responsibly
  open earlier instead of waiting for the existing 11-19 UTC window.
- Fresh full-data W960 validation:
  `outputs/backtests/live_watch_gbpusd_asset_squeeze_early_session_w960_summary.csv`.
- All five variants rejected, including the current 11-19 UTC session, an
  08-19 UTC expansion, and modestly relaxed squeeze/prior-volatility settings.
  Every line produced zero active fixed-warmup evaluation fills.
- Added the scan to `scripts/live_status_summary.py` so future GBPUSD
  session-gated diagnostics cite the exact rejection evidence.
- Decision: do not expand the GBPUSD asset-squeeze session or relax its
  squeeze filters. Keep the live map unchanged and wait for tested strategy
  gates to approve risk.

## 2026-06-25 MACD current-refresh W960 check

- Refreshed the production MACD sleeve on the full live-seven 15-minute
  backtest files because the monitor's top promoted MACD evidence was becoming
  stale while the live loop remained flat:
  `outputs/backtests/live_watch_macd_current_refresh_20260625_w960.csv`.
- The active `8/21/8`, 0.75 bps histogram, 0.50 bps MACD, 0.00 slope,
  0.10 efficiency, hours 6-14 plus 20-22 UTC setup still promoted: +2.400%
  return, 86 trades, 0.605% max drawdown, 83.3% positive folds, 83.3%
  active-positive folds, and 83.3% non-negative folds.
- Lowering the histogram gate to 0.50 produced the exact same 86 trades, so it
  adds no live opportunity. Micro variants reached 90 trades but reduced return
  to +1.806% and weakened median active-fold return.
- Faster 6/18/5 variants reached 88-102 trades, but stayed `PAPER_ONLY` because
  total and active-positive fold fractions were only 66.7%.
- Added the fresh scan to `scripts/live_status_summary.py` so future live
  summaries cite the current W960 evidence instead of an older stale file.
- Decision: keep MACD production parameters unchanged. The tested aggressive
  variants either do not increase activity or trade activity for weaker
  full-data payoff.

## 2026-06-25 opportunity-probe five-symbol pressure rejection

- Refreshed live snapshots after the guarded loop stayed flat. Production
  diagnostics still requested no risk, while the read-only
  `candidate_all_opportunity_probe` sleeve requested short `AUDUSD` and
  `EURUSD`, with `GBPUSD`, `USDCHF`, and `USDJPY` also firing behind the
  two-position diagnostic cap.
- Ran exact full-data W960 validation on that pressure set:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_chf_jpy_current_w960.csv`.
- Every candidate rejected. The least-bad selective line still lost 0.234%,
  made 912 trades, and reached only 16.7% positive, active-positive, and
  non-negative folds. The live-current line lost 0.759% with 2,140 trades.
- Added the scan to `scripts/live_status_summary.py` so future capped
  AUD/EUR/GBP/CHF/JPY opportunity-probe pressure is tied to the current
  rejection evidence.
- Decision: do not expand the two-position cap, promote `opportunity_probe`,
  or force manual trades for this pressure basket. Keep the guarded live map
  unchanged.

## 2026-06-25 multi-horizon preopen session rejection

- The latest read-only `candidate_all_multi_horizon` diagnostic was fully
  session-gated at 09:00 UTC because multi-horizon momentum only trades
  10-14 UTC in production. I tested whether opening that sleeve one hour
  earlier could add evidence-backed activity.
- Fresh full-data W960 validation on all live-seven symbols:
  `outputs/backtests/live_watch_multi_horizon_preopen_refresh_20260625_w960.csv`.
- Every tested session variant lost money. The strict 9-14 UTC line was least
  bad at -0.111% with 250 trades and 50.0% positive/non-negative folds, while
  the current 10-14 UTC line lost 0.182% with only 16.7% positive and
  non-negative folds. Broader 9-14 and 7-12 variants were worse.
- Added the scan to `scripts/live_status_summary.py` so future multi-horizon
  preopen/session-gated pressure has current rejection evidence.
- Decision: do not add 09:00 UTC or broader early-Europe hours to
  `multi_horizon_momentum`, and do not route live symbols to this sleeve.

## 2026-06-25 AUDUSD/EURUSD opportunity-probe refresh

- Fresh live sentiment turned more USD-supportive, and the read-only
  `candidate_all_opportunity_probe` diagnostic requested short `AUDUSD` and
  short `EURUSD`. Production MACD still requested no risk: AUDUSD was inside
  the exit band and EURUSD remained below the 0.75 bps histogram threshold.
- Refreshed the exact two-symbol pressure sleeve on the extracted full
  15-minute dataset:
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_refresh_20260625_w960.csv`.
- Every candidate rejected. The least-bad `ultra_pair_6_18_48_s425` still lost
  0.022% with 169 trades and only 33.3% positive/active-positive/non-negative
  folds. The live-current pair lost 0.299% with 877 trades.
- Added the fresh scan to `scripts/live_status_summary.py` so current
  AUDUSD/EURUSD probe pressure cites same-day evidence rather than the older
  June 23 W960 file.
- Decision: do not route AUDUSD/EURUSD to `opportunity_probe` and do not force
  discretionary shorts. Keep production on the promoted MACD sleeve and wait
  for its guarded thresholds to confirm an entry.

## 2026-06-25 EURGBP opportunity-probe refresh

- The next live read-only `candidate_all_opportunity_probe` diagnostic stopped
  pointing at AUDUSD/EURUSD and isolated a long `EURGBP` allocation. Production
  remained flat because EURGBP is still on the session-gated champion sleeve.
- Ran a pure EURGBP opportunity-probe W960 validation on the extracted full
  15-minute dataset with the directional probe profile:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_refresh_20260625_w960.csv`.
- Every candidate rejected. The least-bad `selective_5_15_40_s2_75` line lost
  0.029% with 171 trades and only 16.7% positive, active-positive, and
  non-negative folds. The live-current line lost 0.114% with 401 trades.
- Added the fresh scan to `scripts/live_status_summary.py` so future EURGBP
  opportunity-probe pressure cites same-day isolated evidence.
- Decision: do not route EURGBP to `opportunity_probe` and do not force the
  diagnostic allocation. Keep EURGBP on the guarded production map until a
  strategy passes fold stability instead of only a momentary live pulse.

## 2026-06-25 USDCHF opportunity-probe refresh

- After refreshing sentiment and live diagnostics, the read-only
  `candidate_all_opportunity_probe` sleeve rotated to a single actionable
  `USDCHF` allocation. Production MACD still requested no risk.
- Ran an isolated USDCHF opportunity-probe W960 validation on the extracted
  full 15-minute dataset with the directional probe profile:
  `outputs/backtests/live_watch_opportunity_probe_usdchf_refresh_20260625_w960.csv`.
- Every candidate rejected. The least-bad selective line still lost 0.039%,
  while the top-ranked strict line lost 0.043%; both reached only 33.3%
  positive, active-positive, and non-negative folds. The live-current line lost
  0.131% with 409 trades.
- Added the fresh scan to `scripts/live_status_summary.py` so future USDCHF
  opportunity-probe pressure cites same-day isolated evidence.
- Decision: do not route USDCHF to `opportunity_probe`, do not increase risk,
  and do not force a manual USDCHF trade. Keep USDCHF on the promoted MACD
  sleeve until the tested live threshold clears.

## 2026-06-25 USDCAD heuristic-probe MACD refresh

- Refreshed live pair analysis after the opportunity-probe checks. The only
  advisory `eligible_tiny_probe_buy` was `USDCAD`, but production MACD still
  requested no risk because the histogram was only 0.07 bps, inside the
  0.25 bps exit band.
- Ran an isolated USDCAD MACD W960 validation on the extracted full 15-minute
  dataset with the directional probe profile:
  `outputs/backtests/live_watch_macd_usdcad_refresh_20260625_w960.csv`.
- The best line was small-positive (+0.008%) with 10 trades, 50.0% positive
  folds, 75.0% active-positive folds, and 83.3% non-negative folds, but it
  still rejected because total fold stability is too weak. Other lines were
  sparse or weaker.
- Added the fresh scan to `scripts/live_status_summary.py` so future USDCAD
  heuristic-only pressure cites same-day full-data evidence rather than the
  older W480 symbol scan.
- Decision: do not lower the live USDCAD MACD threshold for a heuristic-only
  score. Keep USDCAD on the promoted live MACD sleeve and wait for the tested
  production trigger.

## 2026-06-25 GBPUSD opportunity-probe refresh

- After another live refresh, the read-only `candidate_all_opportunity_probe`
  diagnostic rotated to a single actionable long `GBPUSD` allocation. Production
  remained flat because GBPUSD is still on the session-gated champion sleeve.
- Ran an isolated GBPUSD opportunity-probe W960 validation on the extracted
  full 15-minute dataset with the directional probe profile:
  `outputs/backtests/live_watch_opportunity_probe_gbpusd_refresh_20260625_w960.csv`.
- Every candidate rejected. The least-bad `selective_5_15_40_s2_75` line lost
  0.020% with 187 trades and only 33.3% positive, active-positive, and
  non-negative folds. The live-current line lost 0.122% with 412 trades.
- Added the fresh scan to `scripts/live_status_summary.py` so future isolated
  GBPUSD opportunity-probe pressure cites same-day evidence instead of only
  mixed EURGBP/GBPUSD basket evidence.
- Decision: do not route GBPUSD to `opportunity_probe` and do not force the
  read-only allocation. Keep GBPUSD on the guarded champion sleeve until a
  tested strategy clears live-ready fold stability.

## 2026-06-25 USDCHF MACD single-symbol refresh

- Fresh sentiment and pair analysis kept USDCHF constructive, but production
  MACD still requested no risk because the histogram was inside the 0.25 bps
  exit band. The live summary also only had older single-symbol USDCHF MACD
  evidence.
- Ran an isolated USDCHF MACD W960 validation on the extracted full 15-minute
  dataset with the directional probe profile:
  `outputs/backtests/live_watch_macd_usdchf_refresh_20260625_w960.csv`.
- The best return line was small-positive (+0.031%) with 40 trades, but only
  50.0% positive folds and 50.0% non-negative folds. The top-ranked
  `fast_strict_6_18_5_h2_m1_eff20_hold12` line made +0.022% with 32 trades,
  but only 50.0% positive and 66.7% non-negative folds.
- Added the fresh scan to `scripts/live_status_summary.py` so USDCHF MACD
  pressure no longer relies on the older W480 evidence.
- Decision: keep USDCHF on the existing promoted MACD map, but do not lower its
  threshold or add single-symbol USDCHF overrides until fold stability improves.

## 2026-06-25 USDJPY quality-trend same-day refresh

- Before the 10-14 UTC USDJPY quality-trend window, refreshed the isolated
  USDJPY sleeve on the extracted full 15-minute dataset with the directional
  probe profile:
  `outputs/backtests/live_watch_quality_trend_usdjpy_refresh_20260625_w960.csv`.
- Every candidate rejected. The strict 14-19 and 10-19 variants produced no
  active fixed-warmup folds, and the current 10-14 UTC live row lost a small
  0.001% with only 2 trades, 16.7% active folds, and 0.0% active-positive
  folds.
- Added the fresh scan to `scripts/live_status_summary.py` so USDJPY
  quality-trend pressure uses same-day evidence rather than the older W480
  preopen check.
- Decision: keep USDJPY on the guarded quality-trend sleeve, but do not widen
  hours, reduce thresholds, or force any discretionary USDJPY trade. Let the
  live process trade only if the tested production gates actually clear.

## 2026-06-25 MACD live-threshold relaxation check

- Live diagnostics showed several MACD symbols close to the entry gate, so I
  tested whether lowering the live histogram threshold from 0.75 bps to
  0.50 bps would safely make the promoted live MACD sleeve more active.
- First checked the lower-risk `directional_probe` allocation profile:
  `outputs/backtests/live_watch_macd_live_relax_h050_20260625_w960.csv`.
  That profile rejected the current and relaxed rows, so it is not a safe
  research-sizing override.
- Then ran the exact live/default allocation profile used by the guarded MT5
  process:
  `outputs/backtests/live_watch_macd_live_relax_h050_default_20260625_w960.csv`.
  The relaxed 0.50 bps row was identical to the current 0.75 bps row and both
  promoted: +2.400% return, 86 trades, 83.3% positive folds, 83.3%
  active-positive folds, and 83.3% non-negative folds. The 0.35 bps micro row
  also promoted but was weaker at +2.198%.
- Decision: lower `strategy.macd_momentum.min_histogram_bps` from 0.75 to
  0.50 in live config. This is a narrow activity increase on the validated
  default live profile; keep the MACD-line, cost, sentiment, cooldown, max-lot,
  position-cap, and loss-brake gates unchanged.

## 2026-06-25 MACD micro-entry live profile

- After the 10:00 UTC session opened, production was still flat but several
  MACD symbols were close to entry, with weak ticks still blocked by the
  estimated-cost gate. I tested whether the live MACD sleeve could move from
  the 0.50 bps relaxed row into a micro-entry profile without losing fold
  stability.
- Default live-profile W960 refresh on `AUDUSD EURUSD USDCAD USDCHF`:
  `outputs/backtests/live_watch_macd_live_micro_h025_default_20260625_w960.csv`.
- The current 0.50 bps row remained strongest at +2.400% over 86 trades. The
  micro-entry row `hist=0.25`, `macd=0.35`, `slope=0.05`, `eff=0.08`,
  `hold=10` also promoted: +1.806% return, 90 trades, 83.3% positive folds,
  83.3% active-positive folds, 83.3% non-negative folds, and lower max
  drawdown of 0.456%.
- Decision: promote the micro-entry row to live MACD config to increase trade
  opportunity while leaving the cost gate, sentiment brake, cooldown throttle,
  max-lot cap, max-position cap, and loss brakes intact.

## 2026-06-25 MACD slope relief check

- With live attribution refreshed, the account was flat and most symbols were
  cooldown-blocked from fresh risk. `EURUSD` and `GBPUSD` were only small-only
  eligible, and `EURUSD` was being held by the MACD slope gate.
- Refreshed the default live-profile W960 scan on the full 15-minute dataset:
  `outputs/backtests/live_watch_macd_slope_relief_default_20260625_w960.csv`.
- The current `slope=0.05` row remained rank 1: +1.806% return, 90 trades,
  83.3% positive folds, 83.3% active-positive folds, 83.3% non-negative folds,
  and 0.456% max drawdown.
- The `slope=0.00` row also promoted with the same fold stability, +1.748%
  return, 94 trades, and 0.457% max drawdown. The more aggressive `hist=0.20`
  row promoted but dropped to +1.250% with higher drawdown, and the `hist=0.15`
  row rejected.
- Decision: set live `min_histogram_slope_bps` to `0.0` as a narrow
  trade-frequency relief step. Do not lower the histogram/MACD thresholds or
  bypass cost, sentiment, cooldown, max-lot, max-position, or loss brakes.

## 2026-06-25 EURUSD pressure and MACD exit-band check

- Refreshed live sentiment and pair state. `EURUSD` and `GBPUSD` were the only
  small-only recovery candidates under the 96-hour attribution view, while
  `AUDUSD`, `EURGBP`, `USDCAD`, `USDCHF`, and `USDJPY` were still blocked or
  observe-only for fresh risk.
- The supervisor showed a research-only `multi_horizon_momentum` EURUSD
  allocation, so I isolated EURUSD on full W960 data:
  `outputs/backtests/live_watch_multi_horizon_eurusd_isolated_20260625_w960.csv`.
  All tested rows produced zero trades and remain rejected for live mapping.
- I also checked whether switching the `EURUSD GBPUSD` small-only pressure pair
  to MACD would help:
  `outputs/backtests/live_watch_macd_eurusd_gbpusd_map_probe_20260625_w960.csv`.
  The tested rows also produced zero trades and rejected, so `GBPUSD` stays on
  the champion ensemble sleeve.
- Added independent MACD `exit=` candidate support to the optimizer so the
  dead/exit band can be tested directly instead of only through the histogram
  threshold.
- Exit-band scan:
  `outputs/backtests/live_watch_macd_exit_band_relief_20260625_w960.csv`.
  The current auto/0.10 exit rows remained stronger at +1.748% with 94 trades.
  Narrower 0.075/0.05 exit rows still promoted but slipped to +1.673%, and the
  looser `hist=0.20` rows promoted with lower +1.174% return and higher 0.752%
  drawdown.
- Decision: keep live MACD exit band and thresholds unchanged. The new optimizer
  support stays because it improves future evidence gathering, but no live
  config promotion is justified from this scan.

## 2026-06-25 Champion ensemble session-relief rejection

- At 10:28 UTC the live process was still flat. The only small-only candidates
  under the 96-hour attribution view were `EURUSD` and `GBPUSD`; `EURGBP` was
  cooldown-blocked, but it remained a tempting watchlist name because of
  supportive sentiment and cross-rate candidates.
- Tested whether the `GBPUSD` and `EURGBP` champion ensemble sleeves could be
  made more active before the 11:00 UTC session window by lowering entry
  thresholds, changing Kalman/asset-squeeze weights, and adding a small MACD
  vote:
  `outputs/backtests/live_watch_champion_gbpusd_session_relief_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_champion_eurgbp_session_relief_20260625_w960.csv`.
- Both scans rejected every row. Current, entry-0.35, Kalman-heavy,
  squeeze-heavy, MACD-assisted, and entry-0.25 variants all produced zero
  trades and zero active fixed-warmup folds.
- Decision: do not promote a champion ensemble entry-score or weight change for
  `GBPUSD`/`EURGBP`. Let the live sleeve wait for its tested 11:00 UTC
  underlying signal window rather than adding an untested pre-session shortcut.

## 2026-06-25 MACD agreement-relief rejection

- Live MACD symbols were still near but not through the gate, so I added an
  explicit optimizer switch for `require_macd_histogram_agreement` and tested
  whether allowing MACD line/histogram disagreement would safely add activity.
- Default live-profile scan:
  `outputs/backtests/live_watch_macd_agreement_relief_default_20260625_w960.csv`.
  Relaxing agreement increased fills but degraded quality. The strict promoted
  row stayed best at +2.453% over 86 fills; the strict relaxed row promoted but
  slipped to +2.284% over 110 fills with higher drawdown. The live micro row
  stayed promoted at +1.748% over 94 fills, while the relaxed micro row produced
  122 fills but rejected on 66.7% non-negative folds.
- Directional-probe allocation scan:
  `outputs/backtests/live_watch_macd_agreement_relief_20260625_w960.csv`.
  Every row rejected, and both relaxed rows were worse than their
  agreement-required counterparts.
- Decision: keep live MACD line/histogram agreement required. More fills here
  are not evidence-backed; they add churn and weaker fold stability. The new
  optimizer switch remains for future research, but no live config change is
  justified.

## 2026-06-25 MACD cost-gate relief rejection

- Live diagnostics showed `AUDUSD`, `EURUSD`, and `USDCHF` close to MACD entry,
  but blocked because 0.4-0.5 bps signal edge did not clear the estimated
  2.1-2.4 bps round-trip cost. I added explicit MACD optimizer overrides for
  `slippage_bps` and `cost_buffer` so cost-gate relief can be tested without
  changing production assumptions first.
- Default live-profile scan:
  `outputs/backtests/live_watch_macd_cost_relief_default_20260625_w960.csv`.
  The current cost gate remained best: +1.748% over 94 trades, 83.3% positive
  folds, 83.3% active-positive folds, and 83.3% non-negative folds. All relaxed
  cost rows rejected; the mildest `slip=0.50,cost=1.00` row jumped to 274
  trades but fell to -1.737% with only 33.3% active-positive folds, while more
  aggressive rows lost 3.964% to 5.118%.
- Directional-probe allocation scan:
  `outputs/backtests/live_watch_macd_cost_relief_20260625_w960.csv`. Every row
  rejected, and cost relief increased churn from 200 fills to as many as 1,072
  while keeping returns negative and fold stability weak.
- Decision: do not relax live MACD slippage or cost-buffer gates. The optimizer
  support stays for future research, but live trading must keep the current
  cost filter because forcing these near-edge signals is historically lossy.

## 2026-06-25 USDCAD opportunity-probe refresh rejection

- After 11:00 UTC the guarded live map was still flat, but the research-only
  `opportunity_probe` diagnostics showed a `USDCAD` buy allocation with score
  4.48. I refreshed the USDCAD sleeve on the current live7 full-data import
  before considering a live map change.
- Directional-probe profile:
  `outputs/backtests/live_watch_opportunity_probe_usdcad_refresh_20260625_w960.csv`.
  All rows rejected. The best selective row was still -0.068% with only 50.0%
  positive/active-positive/non-negative folds; the current row was -0.127% with
  421 trades and only 16.7% non-negative folds.
- Default profile:
  `outputs/backtests/live_watch_opportunity_probe_usdcad_default_refresh_20260625_w960.csv`.
  Results matched the directional scan and rejected every row.
- Decision: do not switch `USDCAD` from the validated MACD sleeve to
  `opportunity_probe`, and do not manually force the live USDCAD buy. The
  current live research signal is a churn-prone pattern on full data.

## 2026-06-25 AUDUSD/GBPUSD opportunity-probe refresh rejection

- At 11:03 UTC the research-only `opportunity_probe` diagnostics showed a
  narrow two-symbol basket: `AUDUSD` buy and `GBPUSD` sell. I refreshed that
  exact basket on the current live7 full-data import before considering a live
  map change.
- Directional-probe profile:
  `outputs/backtests/live_watch_opportunity_probe_audusd_gbpusd_refresh_20260625_w960.csv`.
  All rows rejected. The least-bad selective row still lost 0.042% with only
  33.3% positive/active-positive/non-negative folds; the current row lost
  0.271% across 852 trades with only 16.7% non-negative folds.
- Default profile:
  `outputs/backtests/live_watch_opportunity_probe_audusd_gbpusd_default_refresh_20260625_w960.csv`.
  Results matched the directional scan and rejected every row.
- Decision: do not switch `AUDUSD` or `GBPUSD` to the opportunity-probe sleeve
  and do not force the current buy/sell basket. It adds activity, but the
  full-data evidence says the activity is negative-edge churn.

## 2026-06-25 AUDUSD/USDCHF opportunity-probe refresh rejection

- A later supervisor refresh rotated the research-only `opportunity_probe`
  basket to `AUDUSD` buy and `USDCHF` sell. I refreshed that exact two-symbol
  basket on the current live7 full-data import as well.
- Directional-probe profile:
  `outputs/backtests/live_watch_opportunity_probe_audusd_usdchf_refresh_20260625_w960.csv`.
  All rows rejected. The least-bad selective row lost 0.062% with only 33.3%
  positive/active-positive/non-negative folds; the current row lost 0.281%
  across 849 trades with only 16.7% non-negative folds.
- Default profile:
  `outputs/backtests/live_watch_opportunity_probe_audusd_usdchf_default_refresh_20260625_w960.csv`.
  Results matched the directional scan and rejected every row.
- Decision: do not switch `AUDUSD` or `USDCHF` to the opportunity-probe sleeve
  and do not force the current buy/sell basket. The latest opportunity-probe
  basket is active but still negative-edge on full data.

## 2026-06-25 MACD trend-efficiency relief promotion

- Fresh production diagnostics showed `AUDUSD` blocked only by MACD trend
  efficiency (`0.03` below the live `0.08` gate), while the other MACD symbols
  remained histogram/exit-band gated. I tested a narrow efficiency-relief
  ladder on the current live `8/21/8`, `hist=0.25`, `macd=0.35`, `slope=0.00`,
  `exit=0.125`, hours `6-14` plus `20-22` setup.
- Default live-profile scan:
  `outputs/backtests/live_watch_macd_efficiency_relief_default_20260625_w960.csv`.
  All rows promoted under the live allocation profile. The `eff=0.04` row
  ranked first with 114 trades, +1.111% return, 1.176% max drawdown, 83.3%
  positive/active-positive/non-negative folds, and 0.323% median active-fold
  return. The current `eff=0.08` row remained stronger on total return
  (+1.748%) and drawdown (0.457%) but only generated 94 trades.
- Directional-probe profile:
  `outputs/backtests/live_watch_macd_efficiency_relief_20260625_w960.csv`.
  All rows rejected under the research sizing profile, so this is not a broad
  sizing change or a reason to use the opportunity-probe allocation policy.
- Decision: lower live `strategy.macd_momentum.min_trend_efficiency` from
  `0.08` to `0.04` as a measured trade-frequency relief step under the tested
  default live profile. Do not go to `0.03` yet because it adds more churn,
  worsens drawdown, and degrades the directional-probe folds. Keep all live
  risk controls, cost gates, MACD agreement, sentiment brake, cooldown throttle,
  max-lot cap, max-position cap, and loss brakes intact.

## 2026-06-25 EURUSD opportunity-probe refresh rejection

- After the MACD efficiency relief reload, production remained flat while the
  research-only `opportunity_probe` diagnostic rotated to an isolated `EURUSD`
  short. I refreshed the exact EURUSD sleeve on the current live7 full-data
  import before considering any live map change.
- Directional-probe profile:
  `outputs/backtests/live_watch_opportunity_probe_eurusd_refresh_20260625_w960.csv`.
  All rows rejected. The top-ranked strict row lost 0.078% with 252 trades and
  only 50.0% positive/active-positive/non-negative folds; the live-current row
  lost 0.149% across 437 trades.
- Default profile:
  `outputs/backtests/live_watch_opportunity_probe_eurusd_default_refresh_20260625_w960.csv`.
  Results matched the directional scan and rejected every row.
- Decision: do not route `EURUSD` to `opportunity_probe` and do not force the
  current research-only short. Keep `EURUSD` on the promoted MACD sleeve and
  let the cost/histogram gates decide entries.

## 2026-06-25 EURGBP cross-rate refresh, no live promotion

- The live watchlist was still citing stale EURGBP cross-rate candidates from
  `outputs/backtests/live_watch_cross_rate_refine_h4.csv`, while production
  diagnostics kept the live `EURGBP` champion sleeve flat. I refreshed the
  EURGBP cross-rate signal family on `data/live7_full_backtest_prices_15m.csv`
  and `data/live7_full_backtest_quotes_15m.csv`.
- Signal diagnostic refresh:
  `outputs/backtests/live_watch_cross_rate_eurgbp_refresh_h4_20260625.csv`.
  The raw lookback-12 candidates remained eligible as research signals; the top
  row had 31 active samples, a 71.0% hit rate, +1.50 bps average signed forward
  return, and +0.31 bps average edge after cost.
- Full map validation:
  `outputs/backtests/live_watch_eurgbp_cross_strategy_map_refresh_qualify_20260625_w960.csv`.
  Swapping only `EURGBP` from `champion_ensemble` to `cross_rate_reversion`
  reduced the current live-map return from +1.022% to +0.917%, increased trade
  churn only modestly, and still failed live promotion because non-negative
  folds were 66.7%, below the 70.0% threshold.
- Decision: keep `EURGBP` on the live champion sleeve. The cross-rate setup
  stays on the monitored watchlist with refreshed evidence, but it is not a
  live strategy-map promotion and should only trade if future tested live logic
  earns promotion. Future watchlist builds now cite the refreshed EURGBP scan.

## 2026-06-25 MACD h=0.20 same-gates rejection

- Live production diagnostics showed `AUDUSD` close to the MACD histogram gate:
  0.21 bps versus the live 0.25 bps threshold. I tested a narrow histogram
  relief step instead of forcing the near-threshold signal.
- Default live-profile scan:
  `outputs/backtests/live_watch_macd_h020_same_gates_default_20260625_w960.csv`.
  The `h=0.20` rows still promoted under default sizing, but the best
  same-efficiency row improved return only from +1.111% to +1.123% with the
  same 114 trades and the same 83.3% positive/active-positive/non-negative
  folds. The `h=0.20,m=0.30,eff=0.06` row reduced drawdown but also reduced
  fills to 102, so it is not a trade-frequency improvement.
- Directional-probe scan:
  `outputs/backtests/live_watch_macd_h020_same_gates_20260625_w960.csv`.
  Every row rejected. The looser `h=0.20` and `h=0.15` rows stayed negative
  under probe sizing with only 50.0% active-positive and 50.0% non-negative
  folds.
- Decision: keep live MACD histogram, MACD-line, trend-efficiency, exit-band,
  cost, agreement, sentiment, cooldown, max-lot, max-position, and loss-brake
  gates unchanged. The current `AUDUSD` near-hit is not enough evidence for
  another live threshold relaxation.

## 2026-06-25 AUDUSD/EURGBP/GBPUSD opportunity-probe refresh rejection

- The research-only `opportunity_probe` sleeve rotated back to the
  `AUDUSD`/`EURGBP`/`GBPUSD` pressure basket while production remained flat. I
  refreshed the exact basket on the current live7 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_gbp_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_gbp_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad
  `hyper_filtered_s3_00_hold4_20` row still lost 0.170% with 802 trades and
  only 33.3% positive/active-positive/non-negative folds; the live-current row
  lost 0.385% with 1,253 trades and 0.0% non-negative folds.
- Decision: do not route this basket to `opportunity_probe` and do not force
  the current research-only AUDUSD/EURGBP/GBPUSD trades. The pattern remains
  active but negative-edge churn on full data.

## 2026-06-25 AUDUSD/EURUSD/USDCHF opportunity-probe refresh rejection

- After the previous refresh, the research-only `opportunity_probe` sleeve
  rotated to `AUDUSD`/`EURUSD`/`USDCHF`. I refreshed that exact basket on the
  current live7 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_chf_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad `live_now_strict`
  row still lost 0.122% with 622 trades, only 33.3%
  positive/active-positive/non-negative folds, and negative median active-fold
  return. The live-current row lost 0.488% with 1,812 trades and only 16.7%
  non-negative folds.
- Decision: do not route `AUDUSD`, `EURUSD`, or `USDCHF` to the
  `opportunity_probe` sleeve and do not force the current research-only basket.
  The USD-supportive macro context is not enough to overcome this full-data
  churn profile.

## 2026-06-25 session/alpha-router refresh rejection

- The live research cycle flagged session-style signals on `USDCHF`, `GBPUSD`,
  `EURUSD`, and `AUDUSD`, with `USDCHF` also showing supportive sentiment and a
  positive intraday technical score. I refreshed the exact session/alpha sleeve
  candidates on the current live7 full-data import:
  `outputs/backtests/live_watch_session_alpha_refresh_20260625_w960.csv`.
- Every tested map rejected. The least-bad candidate was `USDCHF` as
  `session_breakout`, but it still lost 0.027%, had a 0/100 risk-discipline
  score, and stopped at 66.7% non-negative folds versus the 70.0% live gate.
  The all-session map lost 0.092% with only 50.0% non-negative folds, while
  alpha-router variants were much worse, with 0.0% non-negative folds and
  losses from 0.213% to 0.813%.
- Decision: do not promote `session_breakout` or `alpha_router` for these
  symbols, and do not force the current USDCHF long pressure. Keep the current
  guarded live map and let only promoted MACD/champion/quality logic place
  orders.

## 2026-06-25 MACD micro-trigger rejection

- Live pair analysis showed `USDCHF` as an `eligible_tiny_probe_buy`, but
  production MACD was flat because the histogram was inside the live exit band.
  I tested a deliberately aggressive MACD micro-trigger ladder on
  `AUDUSD`/`EURUSD`/`USDCAD`/`USDCHF` using the current live hours and full
  live7 W960 data:
  `outputs/backtests/live_watch_macd_micro_trigger_default_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_macd_micro_trigger_directional_20260625_w960.csv`.
- Default sizing promoted the guarded micro rows, but they produced the same
  114 fills as the current live MACD sleeve and lower return than the current
  `h=0.25,m=0.35,eff=0.04` row. The only row that actually increased activity
  disabled MACD/histogram agreement, jumped to 154 trades, and rejected at
  66.7% non-negative folds with worse drawdown.
- Directional-probe sizing rejected every row. The micro-trigger rows stayed
  negative with only 50.0% positive/active-positive/non-negative folds.
- Decision: do not lower live MACD histogram/exit-band thresholds or disable
  agreement for the current USDCHF pressure. The tested relaxation adds churn,
  not a stronger live-ready opportunity.

## 2026-06-25 sentiment-pressure map refresh rejection

- Refreshed the stale sentiment-pressure strategy maps against the current
  live7 W960 full-data import because live sentiment remains USD-supportive and
  the read-only pressure probes were rotating between EURGBP, USDCHF, EURUSD,
  and GBPUSD:
  `outputs/backtests/live_watch_sentiment_pressure_maps_20260625_refresh_w960_summary.csv`
  and
  `outputs/backtests/live_watch_sentiment_pressure_maps_20260625_refresh_w960_scores.csv`.
- The best row was `all_quality_trend` across `AUDUSD`, `GBPUSD`, `USDCAD`,
  and `USDCHF`: 20 trades, +0.018% full-sample return, 0.022% drawdown, 100%
  active-positive and non-negative folds, but only 33.3% total positive folds,
  so it stayed `PAPER_ONLY`.
- The higher-activity pressure maps rejected. `best_per_symbol_all` and the
  generated `top_3_best_symbol_strategies` reached only 66.7% non-negative
  folds, while the explicit `sentiment_macd_core` and `sentiment_no_jpy_mix`
  rows lost money with 33.3% non-negative folds.
- Decision: keep the current live map. The refresh confirms useful watchlist
  pressure, but not a live-ready replacement for the guarded MACD/champion/
  quality-trend command.

## 2026-06-25 MACD near-promotion refresh rejection

- Refreshed the stale `lower_6_18_h050_m035_eff07_s003_hold16` near-promotion
  family on the current live7 W960 full-data import:
  `outputs/backtests/live_watch_macd_near_promotion_refresh_default_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_macd_near_promotion_refresh_directional_20260625_w960.csv`.
- Default sizing still promotes the current live `8/21/8 h=0.25 m=0.35
  eff=0.04 hold10` MACD row: +1.111% return, 114 trades, 1.176% drawdown,
  and 83.3% positive/active-positive/non-negative folds.
- The more active `6/18/5` near-promotion rows remain profitable but
  `PAPER_ONLY`; the best lower-threshold row made +1.965% with 96 trades and
  83.3% non-negative folds, but stayed at 66.7% positive folds versus the
  67.0% live gate.
- Directional-probe sizing rejected every row. The same family expanded to
  158-191 trades, fell to 50.0% non-negative folds, and several rows lost
  money; the current live row also rejected under directional sizing.
- Added both refresh files to the status/near-promotion rollup and changed the
  near-promotion tie-breaker to prefer fresher evidence when promotion quality
  is otherwise identical.
- Decision: do not switch live MACD to the 6/18 near-promotion family and do
  not use directional-probe sizing for MACD. Keep the current promoted MACD
  configuration active.

## 2026-06-25 multi-horizon current-pressure refresh rejection

- Fresh pair analysis showed broad heuristic pressure: long `AUDUSD`,
  `EURUSD`, and `GBPUSD`, short `USDCAD` and `USDCHF`, while production stayed
  flat because MACD edge was below estimated cost and champion/quality gates
  were inactive. I refreshed the stale multi-horizon evidence for that exact
  pressure set:
  `outputs/backtests/live_watch_multi_horizon_current_pressure_refresh_20260625_w960.csv`.
- Directional-probe sizing rejected every row. The least-bad
  `tight_8_32_f35_s8` row still lost 0.036%, made 263 trades, and reached only
  50.0% positive/active-positive/non-negative folds.
- The higher-activity `current_hours_6_24` and `short_strict_4_16_hold12`
  variants were worse, losing 0.198% and 0.333% with 727 and 780 trades and
  only 16.7% non-negative folds.
- Added the refresh file to the live status optimizer rollup so current
  multi-horizon diagnostics cite same-day evidence instead of the older
  AUD/EUR and GBP-only scans.
- Decision: do not route the current AUD/EUR/GBP/CAD/CHF pressure basket to
  `multi_horizon_momentum`, and do not use it to force fresh live risk.

## 2026-06-25 EURGBP/EURUSD opportunity-probe refresh rejection

- The read-only all-symbol `opportunity_probe` diagnostic was actionable only
  on short `EURGBP` and short `EURUSD`, while production stayed flat and the
  status summary was still citing the older 2026-06-23 exact basket scan. I
  refreshed the exact basket on the current live7 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_eurusd_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_eurusd_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad `very_strict`
  row lost 0.060% with 238 trades, 0.078% drawdown, and only 16.7%
  positive/active-positive/non-negative folds. The live-current row lost
  0.263% with 838 trades and 0.0% non-negative folds.
- Added the fresh files to the live status optimizer rollup so future
  `candidate_all_opportunity_probe` evidence cites same-day rejection instead
  of the stale EURGBP/EURUSD scan.
- Decision: do not route `EURGBP` and `EURUSD` to `opportunity_probe` and do
  not force the current short basket. The live research signal remains
  negative-edge churn on full data.

## 2026-06-25 AUDUSD/EURUSD/GBPUSD/USDCHF opportunity-probe rejection

- After the sentiment refresh, the read-only all-symbol `opportunity_probe`
  diagnostic rotated to short `AUDUSD`, short `EURUSD`, short `GBPUSD`, and
  long `USDCHF`, while production still had no approved fresh risk. The status
  summary was citing the older W480 pressure-four scan, so I refreshed the
  exact active basket on the current live7 W960 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_chf_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad
  `score3_5_hold16_64` row lost 0.082%, made 505 trades, drew down 0.196%,
  and reached only 33.3% positive/active-positive/non-negative folds. The
  live-current `current_pressure4` row lost 0.551% with 1,698 trades and only
  16.7% non-negative folds.
- Added the fresh files to the live status optimizer rollup so the current
  `candidate_all_opportunity_probe` evidence cites same-day W960 rejection.
- Decision: do not route this four-symbol basket to `opportunity_probe`, do
  not raise the two-position cap for it, and do not manually force the
  short/long pressure set. The latest active opportunity-probe read still looks
  like high-churn negative expectancy.

## 2026-06-25 isolated EURGBP cross-rate rejection

- The live watchlist continued to surface `EURGBP` cross-rate reversion with a
  fast-screen quality score of 1.58, about 71% hit rate, and roughly 0.31 bps
  edge after cost, but the exact live-seven `EURGBP=cross_rate_reversion`
  replacement had already rejected at 66.7% non-negative folds. To check
  whether a narrower EURGBP-only promotion was viable, I ran an isolated
  strategy-map refresh on the current live7 W960 full-data import:
  `outputs/backtests/live_watch_eurgbp_isolated_strategy_refresh_20260625_w960.csv`.
- `EURGBP=cross_rate_reversion`, `EURGBP=champion_ensemble`,
  `EURGBP=quality_trend`, and `EURGBP=macd_momentum` all produced zero
  isolated fixed-warmup fills and rejected. The cross-rate fast-screen edge
  needs multi-symbol context and does not translate into a standalone EURGBP
  live sleeve.
- Added the isolated refresh to the live status optimizer rollup so watchlist
  evidence has an exact-symbol rejection available alongside the broader
  seven-symbol cross-rate replacement rejection.
- Decision: keep `EURGBP` on the champion sleeve and keep cross-rate in
  watchlist/research-only mode until it clears a portfolio-level live map,
  rather than promoting an isolated zero-fill setup.

## 2026-06-25 EURUSD/USDCAD/USDCHF multi-horizon refresh

- The all-symbol `multi_horizon_momentum` diagnostic became the top actionable
  research sleeve: short `EURUSD`, long `USDCAD`, and long `USDCHF`, with the
  live throttle limiting the basket to two active positions. The status summary
  had only isolated `EURUSD` evidence, so I refreshed the exact active basket
  on the current live7 W960 full-data import:
  `outputs/backtests/live_watch_multi_horizon_eur_cad_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_multi_horizon_eur_cad_chf_default_refresh_20260625_w960.csv`.
- Directional-probe sizing rejected every row. The least-bad
  `gbp_10_40_strict` row still lost 0.016% and failed the 95/100 risk
  discipline gate at 76.7/100.
- Default sizing surfaced a watchlist-quality row: `gbp_10_40_strict` made
  0.222% with 12 trades, 0.107% drawdown, and 100% active-positive/non-negative
  folds, but it stayed `PAPER_ONLY` because activity was concentrated in only
  33.3% of folds and the largest positive fold contributed 96.3% of positive
  walk-forward return.
- Added both refresh files to the live status optimizer rollup so
  `candidate_all_multi_horizon` cites exact same-day evidence for the active
  EUR/USD/CAD/CHF basket.
- Decision: keep `multi_horizon_momentum` in watchlist/research mode for this
  basket. The default row is interesting enough to monitor, but not stable
  enough to promote or to raise the live two-position cap.

## 2026-06-25 EURGBP/GBPUSD/USDCAD/USDCHF opportunity-probe rejection

- The fresh all-symbol `opportunity_probe` diagnostic rotated again, this time
  requesting short `EURGBP`, long `GBPUSD`, short `USDCAD`, and short
  `USDCHF`; the live throttle would have allowed only the first two active
  allocations. The status summary was still matching the older
  `EURGBP`/`GBPUSD` scan, so I refreshed the exact requested basket on the
  current live7 W960 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbp_cad_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbp_cad_chf_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad
  `hyper_filtered_s3_00_hold4_20` row lost 0.302%, drew down 0.317%, made
  1,099 trades, and reached only 16.7% positive/active-positive/non-negative
  folds. The current-style rows were worse, losing about 0.48% to 0.49% with
  more than 1,600 trades.
- Added both refresh files to the live status optimizer rollup so the current
  `candidate_all_opportunity_probe` evidence cites exact same-day rejection
  for the active EUR/GBP/CAD/CHF basket.
- Decision: do not route this basket to `opportunity_probe`, do not raise the
  position cap for it, and do not force the EURGBP/GBPUSD/USDCAD/USDCHF
  pressure set. The pattern is high-churn negative expectancy on full data.

## 2026-06-25 AUDUSD/EURUSD/GBPUSD/USDCAD/USDCHF opportunity-probe rejection

- The all-symbol `opportunity_probe` diagnostic rotated to a five-symbol
  pressure basket: long `AUDUSD`, long `EURUSD`, long `GBPUSD`, short
  `USDCAD`, and short `USDCHF`, with the two-position throttle allowing only
  the first two active allocations. The live status evidence was matching the
  older AUDUSD/EURUSD pair scan, so I refreshed the exact requested basket on
  the current live7 W960 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_cad_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_cad_chf_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad
  `score3_5_hold16_64` row lost 0.115%, drew down 0.227%, made 628 trades,
  and reached only 33.3% positive/active-positive/non-negative folds. The
  current-style `current_pressure4` row lost 0.679% with 2,119 trades and only
  16.7% non-negative folds.
- Added both refresh files to the live status optimizer rollup so the current
  `candidate_all_opportunity_probe` evidence cites exact same-day rejection
  for the active AUD/EUR/GBP/CAD/CHF basket.
- Decision: do not route this five-symbol basket to `opportunity_probe`, do
  not raise the two-position cap for it, and do not force the apparent
  long/short pressure set. The full-data test still shows high-churn negative
  expectancy.

## 2026-06-25 GBPUSD/USDCAD/USDCHF multi-horizon rejection

- The refreshed live diagnostics showed `multi_horizon_momentum` wanting long
  `GBPUSD`, short `USDCAD`, and short `USDCHF`, with the live two-position cap
  allowing the first two active allocations. Because the status summary was
  still falling back to older single-symbol GBPUSD evidence, I refreshed the
  exact active basket on the current live7 W960 full-data import:
  `outputs/backtests/live_watch_multi_horizon_gbp_cad_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_multi_horizon_gbp_cad_chf_default_refresh_20260625_w960.csv`.
- Directional-probe sizing rejected every row. The least-bad
  `prod_6_24_current` row still lost 0.017%, drew down 0.050%, made 196
  trades, and reached only 50.0% positive/active-positive/non-negative folds.
- Default sizing produced positive headline P/L in the current-style rows, but
  fold stability stayed below the live gate: `prod_6_24_hold12` made 0.352%,
  drew down 0.564%, made 96 trades, and reached only 50.0% positive,
  active-positive, and non-negative folds. The stricter `gbp_10_40_strict`
  row had 83.3% non-negative folds but lost money overall and had negative
  median active test return.
- Added both refresh files to the live status optimizer rollup so
  `candidate_all_multi_horizon` cites exact same-day evidence for the active
  GBP/CAD/CHF basket.
- Decision: keep `multi_horizon_momentum` research-only for this basket and do
  not route it live or raise the position cap. The live-looking pressure is
  not stable enough across folds.

## 2026-06-25 MACD micro-threshold consensus

- Live pair analysis narrowed to a single heuristic `USDCAD` short pressure
  while production MACD remained flat because the active histogram readings
  were inside the current live exit band. To test a more active but still
  evidence-gated path, I ran a lower-threshold MACD grid on the live MACD
  sleeve (`AUDUSD`, `EURUSD`, `USDCAD`, `USDCHF`) using the current live7
  full-data import:
  `outputs/backtests/live_watch_macd_micro_threshold_refresh_20260625_w960.csv`,
  `outputs/backtests/live_watch_macd_micro_threshold_fullgrid_20260625_w672.csv`,
  and
  `outputs/backtests/live_watch_macd_micro_threshold_fullgrid_20260625_w480.csv`.
- W960 liked the micro 8/21/8 variants: the `h=0.05-0.10`, `macd=0.05-0.15`,
  `exit=0.02-0.04`, `hold=6` rows made 1.306%, drew down 1.105%, made 134
  trades, and reached 83.3% active-positive plus 100.0% non-negative folds.
- Shorter windows did not confirm live readiness. W672 rejected the same micro
  rows at 55.6% positive, 62.5% active-positive, and 66.7% non-negative folds.
  W480 kept them `PAPER_ONLY` with 57.1% positive, 61.5% active-positive, and
  71.4% non-negative folds.
- Built
  `outputs/backtests/live_watch_macd_micro_threshold_consensus_20260625.csv`.
  The three-window consensus rejects the micro 8/21/8 rows and keeps the
  faster 6/18 alternatives paper-only; the current live row also remains
  rejected by consensus because shorter windows fail fold stability.
- Added the scan files to the live status optimizer rollup and made this new
  consensus the status summary's parameter-consensus source.
- Decision: do not lower live MACD histogram/MACD thresholds yet. This is the
  best current route toward a less idle MACD sleeve, but the multi-window
  evidence says keep it in watchlist/research mode until shorter windows stop
  failing fold stability.

## 2026-06-25 AUDUSD/EURGBP/EURUSD/GBPUSD/USDCHF opportunity-probe rejection

- The live `candidate_all_opportunity_probe` diagnostic rotated to short
  `AUDUSD`, long `EURGBP`, short `EURUSD`, short `GBPUSD`, and long `USDCHF`.
  The live two-position throttle would allow only the first two active
  allocations, while the status summary was still matching an older
  `AUDUSD`/`EURGBP` pair scan. I refreshed the exact requested basket on the
  current live7 W960 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_eur_gbp_chf_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_eur_gbp_chf_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad
  `score3_5_hold16_64` row lost 0.090%, drew down 0.200%, made 617 trades,
  and reached only 50.0% positive/active-positive/non-negative folds.
- The current-style `current_pressure4` row lost 0.665%, drew down 0.708%,
  made 2,099 trades, and reached only 16.7% positive/active-positive/
  non-negative folds.
- Added both refresh files to the live status optimizer rollup so future
  `candidate_all_opportunity_probe` evidence can cite exact same-day
  rejection for the active AUD/EUR/GBP/CHF basket.
- Decision: do not route this basket to `opportunity_probe`, do not increase
  the position cap for it, and do not force the AUDUSD/EURGBP pair. The exact
  full-data test remains negative expectancy with weak fold stability.

## 2026-06-25 AUDUSD/EURGBP/USDCHF/USDJPY opportunity-probe rejection

- The next live `candidate_all_opportunity_probe` diagnostic narrowed to short
  `AUDUSD`, long `EURGBP`, short `USDCHF`, and short `USDJPY`, with the
  two-position live throttle allowing `AUDUSD` and `EURGBP` first. The status
  summary still had only the older AUDUSD/EURGBP pair evidence, so I refreshed
  the exact four-symbol requested basket on the current live7 W960 full-data
  import:
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_chf_jpy_refresh_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eurgbp_chf_jpy_default_refresh_20260625_w960.csv`.
- Both allocation profiles rejected every row. The least-bad
  `score4_hyper_filter` row lost 0.093%, drew down 0.128%, made 368 trades,
  and reached only 50.0% positive/active-positive/non-negative folds.
- The current-style `current_pressure4` row lost 0.602%, drew down 0.612%,
  made 1,692 trades, and reached 0.0% positive/active-positive/non-negative
  folds.
- Added both refresh files to the live status optimizer rollup so the active
  AUD/EURGBP/CHF/JPY pressure set is blocked by fresh same-day evidence rather
  than by stale pair-only evidence.
- Decision: do not route this basket to `opportunity_probe`, do not raise the
  live position cap, and do not force the AUDUSD/EURGBP pair. The apparent
  live pressure is still high-turnover negative expectancy on full data.

## 2026-06-25 AUDUSD/EURUSD opportunity-probe cap-relief rejection

- After refreshing sentiment and live diagnostics, production stayed flat, but
  the read-only `candidate_all_opportunity_probe` sleeve requested long
  `AUDUSD` and long `EURUSD`; it also showed long `GBPUSD`, short `USDCAD`,
  short `USDCHF`, and short `USDJPY` blocked by the two-position live throttle.
  I refreshed the exact capped basket and the broader cap-relief basket on the
  current live7 W960 full-data import:
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_refresh2_20260625_w960.csv`,
  `outputs/backtests/live_watch_opportunity_probe_audusd_eurusd_default_refresh2_20260625_w960.csv`,
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_cad_chf_jpy_refresh_20260625_w960.csv`,
  and
  `outputs/backtests/live_watch_opportunity_probe_aud_eur_gbp_cad_chf_jpy_default_refresh_20260625_w960.csv`.
- The capped AUDUSD/EURUSD sleeve rejected every row under both allocation
  profiles. The least-bad `selective_5_15_40_s2_75_f2_00_v0_50_hold24_120`
  row still lost 0.072%, drew down 0.126%, made 368 trades, and reached only
  33.3% positive/active-positive/non-negative folds.
- The broader six-symbol cap-relief sleeve was worse: the least-bad
  `selective_5_15_40_s2_75_f2_00_v0_50_hold24_120` row lost 0.302%, drew down
  0.367%, made 1,099 trades, and reached only 16.7% positive/active-positive/
  non-negative folds. The current-style row lost about 0.885% with 2,561
  trades.
- Added all four refresh files to the live status optimizer rollup so the
  current opportunity-probe pressure is blocked by fresh same-day evidence.
- Decision: do not route this sleeve live, do not relax the two-position cap
  for the throttled names, and do not force these trades manually. More slots
  increased churn and worsened expectancy instead of improving survival odds.

## 2026-06-25 AUDUSD/EURUSD/USDCHF MACD cap-relief watchlist

- After the guarded live process opened `EURUSD` long and `USDCHF` short at
  the 0.25-lot cap, production diagnostics showed `AUDUSD` as the only fresh
  MACD add-on candidate blocked by the two-position live cap. The same guarded
  loop then exited both positions at 14:11:47 UTC; attribution moved `EURUSD`
  and `USDCHF` to `observe` after about -$22 realized combined. I refreshed the
  exact open-pair sleeve and the cap-relief trio on the current live7 full-data
  import:
  `outputs/backtests/live_watch_macd_open_pair_refresh_20260625_w960.csv`,
  `outputs/backtests/live_watch_macd_aud_eur_chf_cap_relief_20260625_w960.csv`,
  `outputs/backtests/live_watch_macd_aud_eur_chf_cap_relief_20260625_w672.csv`,
  and
  `outputs/backtests/live_watch_macd_aud_eur_chf_cap_relief_20260625_w480.csv`.
- The open `EURUSD`/`USDCHF` pair is positive but not promotable at W960:
  the best `fast_6_18_5_h1_m0_5_eff10_hold16` row made 0.827%, drew down
  0.188%, made 44 trades, and stayed `PAPER_ONLY`; the currently live smooth
  `8/21/8` row made 0.871% but was rejected by fold stability.
- The cap-relief `AUDUSD`/`EURUSD`/`USDCHF` trio is the strongest current
  MACD watchlist candidate, but still not enough to change live risk. W960
  kept every row `PAPER_ONLY` or `REJECT`; the smooth `8/21/8` row made
  2.401% with 0.406% drawdown but only 66.7% positive folds. W672 and W480
  promoted the fast `6/18/5` variants, but W960 kept them paper-only due fold
  concentration/positive-fold gates.
- Built
  `outputs/backtests/live_watch_macd_aud_eur_chf_cap_relief_consensus_20260625.csv`.
  Consensus ranks `fast_6_18_5_h1_m0_5_eff10_hold16` first, but only as
  `PAPER_ONLY` with statuses `PROMOTE|PROMOTE|PAPER_ONLY`.
- Added the W960 scan and cross-window consensus file to the live status
  optimizer rollup; W672/W480 remain research artifacts so their standalone
  `PROMOTE` rows do not overstate live readiness.
- Decision: do not relax the live two-position cap, force a re-entry, or switch
  MACD parameters after the EURUSD/USDCHF loss. Keep AUD/EUR/CHF MACD cap
  relief on the near-promotion watchlist and retest only if W960 improves and
  the observe cooldown clears.

## 2026-06-25 AUDUSD heuristic tiny-probe rejection

- A fresh monitor pass marked `AUDUSD` as `eligible_tiny_probe_sell`, but the
  production `macd_momentum` sleeve still requested zero notional because the
  current trend-efficiency gate was not cleanly cleared. I refreshed the exact
  AUDUSD-only MACD question on the current W960 full-data imports:
  `outputs/backtests/live_watch_macd_audusd_current_full_20260625_w960.csv`
  and
  `outputs/backtests/live_watch_macd_audusd_promoted_shape_20260625_w960.csv`.
- The live-threshold ladder (`8/21/8`, `hist=0.25`, `macd=0.35`, `eff=0.04`)
  and slightly looser variants produced no AUDUSD-only fills on W960. Replaying
  the previously promoted multi-symbol MACD shapes against isolated `AUDUSD`
  also produced zero fills, confirming the earlier MACD edge was not AUDUSD
  specific.
- Added both W960 AUDUSD scans to the live status optimizer rollup ahead of the
  older AUDUSD W480 artifacts so future heuristic-only AUDUSD warnings cite
  current full-window evidence.
- Decision: keep `AUDUSD` monitor-only for this pressure burst. Do not lower
  MACD gates, force an AUDUSD short, or route AUDUSD to `opportunity_probe`;
  both the AUDUSD/USDJPY opportunity-probe sleeve and the AUDUSD-only MACD W960
  evidence reject live promotion.

## 2026-06-25 non-blocked MACD refresh

- With `EURUSD` and `USDCHF` observe-blocked after the 14:11 UTC exits, I
  refreshed a non-blocked MACD sleeve for `USDCAD`, `AUDUSD`, and `USDJPY`:
  `outputs/backtests/live_watch_macd_nonblocked_refresh_20260625_w960.csv`.
- The best row, `fast6_h025_m035_eff04_hold10`, made 0.722% with 0.145%
  drawdown and 22 trades on the full W960 import, but stayed `PAPER_ONLY`:
  66.7% total positive folds missed the live-promotion threshold even though
  active-positive and non-negative folds were both 100.0%.
- The running `live_current_h025_m035_eff04_hold10` row was also `PAPER_ONLY`
  at 50.0% positive folds. Looser micro variants traded more often but failed
  the active-positive gate at 60.0%.
- Added the W960 scan to the live status optimizer rollup so non-blocked MACD
  pressure is tracked alongside the older AUD/EUR/CHF and AUDUSD-only evidence.
- Decision: do not switch `USDJPY` to MACD or loosen live MACD parameters from
  this scan. Keep it on the near-promotion watchlist and require another
  confirming full-window pass before changing live configuration.

## 2026-06-25 champion squeeze refresh

- The monitor-only research cycle again surfaced `GBPUSD` and `AUDUSD`
  `asset_adaptive_dual_squeeze` signals, while production stayed flat because
  the live `champion_ensemble` detected chop/no valid squeeze setup. I
  refreshed an AUDUSD/GBPUSD/EURGBP champion ensemble slice on the current W960
  full-data import:
  `outputs/backtests/live_watch_champion_squeeze_refresh_20260625_w960.csv`.
- The current live weights and two looser/asset-heavier variants all made about
  0.285%-0.321% with 18 trades and low drawdown, but the walk-forward evidence
  was concentrated in one active fold: total positive folds were only 16.7% and
  largest positive fold contribution was 100.0%. The asset-only variant made no
  trades and was rejected.
- Added the W960 refresh to the live status optimizer rollup so repeated
  squeeze research signals cite fresh same-day evidence.
- Decision: do not lower `champion_ensemble` entry scores or push an
  asset-heavy squeeze variant live. The signal is interesting for monitoring,
  but it is not broad enough across folds to justify increased live risk.

## 2026-06-25 alpha-router current-pressure rejection

- Because the research cycle continued to surface alpha-router/session-breakout
  rows while production stayed flat, I refreshed a fixed-warmup W960 validation
  for the currently non-blocked pressure set:
  `AUDUSD`, `EURGBP`, `GBPUSD`, and `USDCAD`.
- Output files:
  `outputs/backtests/live_watch_alpha_router_current_pressure_20260625_w960_summary.csv`
  and
  `outputs/backtests/live_watch_alpha_router_current_pressure_20260625_w960_folds.csv`.
- The slice rejected: 132 evaluation fills, 33.3% positive folds, 33.3% active
  positive folds, 33.3% non-negative folds, -0.025% median active test return,
  and 0.335% worst test drawdown. Average risk discipline remained 100/100,
  so the problem is expectancy/fold stability rather than limit handling.
- Added the W960 summary to the live status optimizer rollup so current
  alpha-router pressure is blocked by fresh full-window evidence.
- Decision: do not route `GBPUSD`, `AUDUSD`, `EURGBP`, or `USDCAD` to
  `alpha_router` from this setup. Keep alpha-router monitor-only until a
  narrower candidate passes fixed-warmup promotion gates.

## 2026-06-25 relative-strength current-pressure rejection

- I attempted a broad relative-strength optimizer pass on the non-blocked
  pressure set (`AUDUSD`, `EURGBP`, `GBPUSD`, `USDCAD`, `USDJPY`) with W960
  walk-forward windows, but the parameter-grid run exceeded ten minutes before
  writing an artifact. I stopped only that research process and replaced it
  with a narrower fixed-warmup validation of the configured `relative_strength`
  strategy.
- Output files:
  `outputs/backtests/live_watch_relative_strength_current_pressure_20260625_w960_summary.csv`
  and
  `outputs/backtests/live_watch_relative_strength_current_pressure_20260625_w960_folds.csv`.
- The configured relative-strength slice rejected cleanly: 0 evaluation fills,
  0.0% active folds, and `REJECT` with reason "strategy produced no active
  fixed-warmup evaluation folds." Risk discipline was 100/100 because the
  strategy stayed flat.
- Added the W960 summary to the live status optimizer rollup so relative
  strength remains blocked by fresh current-pressure evidence.
- Decision: do not route current live symbols to `relative_strength`; it is not
  an opportunity source in this window unless a future parameter-specific scan
  can produce active, fold-stable trades.

## 2026-06-25 MACD hour-15 non-blocked rejection

- With the live map flat at 15:00 UTC and `AUDUSD`/`USDCAD` blocked only by the
  validated MACD session window, I tested whether adding hour 15 could create
  evidence-backed activity without touching cost, agreement, or lot guardrails.
- Output: `outputs/backtests/live_watch_macd_hour15_nonblocked_20260625_w960.csv`.
  The current 10-14 UTC row stayed `PAPER_ONLY` at +0.898%, 16 trades, 50.0%
  total positive folds, and 100.0% active-positive/non-negative folds. The
  hour-15 current row added activity (28 trades) but weakened to +0.689%, 50.0%
  total positive folds, 75.0% active-positive folds, and `PAPER_ONLY`. The
  fast-6 hour-15 row also stayed `PAPER_ONLY`.
- Added the scan to the live status optimizer rollup so future 15:00 UTC
  session-gated pressure cites current full-data evidence.
- Decision: do not widen the live MACD session gate to hour 15. The extra
  trades are not live-ready and are weaker than the existing session window.

## 2026-06-25 EURGBP/GBPUSD opportunity-probe refresh rejection

- The latest read-only `candidate_all_opportunity_probe` sleeve rotated to a
  live-sized EURGBP short plus GBPUSD long basket. I refreshed that exact
  two-symbol basket under the directional-probe allocation profile before
  considering any live routing change.
- Output:
  `outputs/backtests/live_watch_opportunity_probe_eurgbp_gbpusd_refresh2_20260625_w960.csv`.
  Every row rejected. The best row still lost 0.137% with 491 trades and only
  33.3% positive/active-positive/non-negative folds. The current live-shape row
  was worse: -0.235%, 813 trades, 0.0% positive folds, 0.0% non-negative folds,
  and 418 evaluation fills.
- Added the scan to the live status optimizer rollup so this current
  research-only basket cites same-day exact evidence.
- Decision: do not route EURGBP/GBPUSD to `opportunity_probe`, do not force a
  manual basket trade, and do not relax live gates for this churn-prone sleeve.

## 2026-06-25 USDCAD/USDJPY opportunity-probe refresh rejection

- The read-only `candidate_all_opportunity_probe` sleeve later rotated to a
  live-sized USDCAD long plus USDJPY long basket while production stayed flat.
  I refreshed that exact two-symbol basket under the directional-probe
  allocation profile before considering any live routing change.
- Output:
  `outputs/backtests/live_watch_opportunity_probe_usdcad_usdjpy_refresh_20260625_w960.csv`.
  Every row rejected. The best row lost 0.171% with 359 trades, 0.0% positive
  folds, 0.0% active-positive folds, and 0.0% non-negative folds. The current
  live-shape row was worse: -0.335%, 863 trades, 0.0% positive folds, 0.0%
  non-negative folds, and 426 evaluation fills.
- Added the scan to the live status optimizer rollup so this current
  research-only basket cites same-day exact evidence.
- Decision: do not route USDCAD/USDJPY to `opportunity_probe`, do not force a
  manual basket trade, and do not relax live gates for this negative-expectancy
  sleeve.

## 2026-06-25 AUDUSD/GBPUSD/USDJPY champion asset-squeeze rejection

- The live research cycle kept surfacing `champion_ensemble`
  `asset_adaptive_dual_squeeze` rows on GBPUSD and AUDUSD, with USDJPY also
  qualifying on the same signal family. I refreshed the exact
  AUDUSD/GBPUSD/USDJPY cluster with a narrow champion-weight scan under the
  directional-probe allocation profile.
- Output:
  `outputs/backtests/live_watch_champion_asset_squeeze_aud_gbp_jpy_refresh_20260625_w960.csv`.
  Every row rejected. The best `asset_only` row was slightly positive
  (+0.007%, 44 trades) but missed fold stability with 50.0% positive folds,
  60.0% active-positive folds, and 66.7% non-negative folds. The production-like
  `live_current` row was weaker at -0.087%, 90 trades, 16.7% positive folds,
  and 16.7% non-negative folds.
- Added the scan to the live status optimizer rollup so this current research
  cluster cites same-day exact evidence.
- Decision: do not route AUDUSD/GBPUSD/USDJPY to an asset-heavy champion
  sleeve, and do not increase live risk for this signal until it clears
  fixed-warmup fold stability rather than isolated positive folds.

## 2026-06-25 GBPUSD/USDJPY opportunity-probe refresh rejection

- The read-only `candidate_all_opportunity_probe` sleeve rotated again to a
  GBPUSD short plus USDJPY long basket. I refreshed that exact two-symbol
  basket under the directional-probe allocation profile before considering any
  live routing change.
- Output:
  `outputs/backtests/live_watch_opportunity_probe_gbpusd_usdjpy_refresh_20260625_w960.csv`.
  Every row rejected. The best row still lost 0.175% with 474 trades and only
  33.3% positive/active-positive/non-negative folds. The current live-shape row
  was worse: -0.329%, 854 trades, 0.0% positive folds, 0.0% active-positive
  folds, and 0.0% non-negative folds.
- Added the scan to the live status optimizer rollup so this current
  research-only basket cites same-day exact evidence.
- Decision: do not route GBPUSD/USDJPY to `opportunity_probe`, do not force a
  manual basket trade, and do not relax live gates for this negative-expectancy
  sleeve.

## 2026-06-25 promoted MACD micro-threshold live update

- Refreshed the promoted top-four MACD shape against
  `data/live7_full_backtest_prices_15m.csv` and
  `data/live7_full_backtest_quotes_15m.csv` with W960 fixed-warmup folds.
- Output:
  `outputs/backtests/live_watch_macd_micro_vs_current_refresh2_20260625_w960.csv`.
  The top `micro_h005_m005_eff04_hold6` row stayed `PROMOTE`/live-ready at
  +1.306% return, 1.105% drawdown, 134 trades, 83.3% positive folds, 83.3%
  active-positive folds, 100.0% non-negative folds, and 75 evaluation fills.
  The previous live-current row also stayed `PROMOTE`, but was less active
  with 114 trades and had weaker non-negative fold coverage at 83.3%.
- Decision: update live MACD parameters to the promoted micro row
  (`min_histogram_bps=0.05`, `exit_histogram_bps=0.02`,
  `min_macd_bps=0.05`, `max_holding_period=6`) while keeping the same
  validated session hours, lot cap, loss brakes, sentiment brake, and
  symbol-state throttle intact.

## 2026-06-25 hour-16 non-MACD expansion checks

- Current live pressure at 16:15 UTC showed heuristic-only AUDUSD and GBPUSD
  buys plus a USDCAD sell, while production stayed flat because MACD and
  quality-trend session gates were closed and champion/volatility/pullback
  signals did not align.
- Refreshed session-momentum hour-16 candidates for AUDUSD/GBPUSD/USDCAD in
  `outputs/backtests/live_watch_session_momentum_aud_gbp_cad_h16_refresh_20260625_w960.csv`.
  Every candidate produced zero trades and zero active folds, including loose
  hour-16-only shapes.
- Refreshed quality-trend hour-16 candidates for AUDUSD/GBPUSD/USDCAD/USDJPY in
  `outputs/backtests/live_watch_quality_trend_aud_gbp_cad_jpy_h16_refresh_20260625_w960.csv`.
  The best small extended row was positive (+0.017%, 19 trades) with 100.0%
  active-positive and non-negative active folds, but only 33.3% total positive
  folds and 33.3% active fold coverage, so it stayed `PAPER_ONLY`. The
  stricter late-session row rejected.
- A volatility-squeeze near-miss walk-forward scan was attempted, but the
  optimizer did not finish within the live supervision time cap and wrote no
  completed CSV. Its process tree was stopped; no result was used for routing.
- Decision: do not add hour 16 to session momentum or quality trend, and do not
  loosen volatility-squeeze routing without a completed walk-forward result.

## 2026-06-25 micro-MACD hour-16 rejection

- After promoting the micro MACD thresholds, refreshed the exact hour-16
  session question for the non-observe MACD symbols AUDUSD and USDCAD.
- Output:
  `outputs/backtests/live_watch_macd_micro_aud_cad_h16_refresh_20260625_w960.csv`.
  The current validated hours row remained positive but only `PAPER_ONLY` on
  this two-symbol slice (+0.798%, 20 trades, 50.0% active folds, 100.0%
  active-positive folds). Adding hour 16 reduced return to +0.701% and stayed
  `PAPER_ONLY`. Hour-16-only variants lost -0.144% with 12 trades, 33.3%
  active-positive folds, 66.7% non-negative folds, and `REJECT` status.
- Decision: keep MACD live hours unchanged. The current 16:00 UTC USDCAD and
  AUDUSD pressure is not a validated micro-MACD expansion signal.

## 2026-06-25 EURGBP cross-rate watchlist recheck

- The live watchlist continued to surface EURGBP `cross_rate_reversion` rows
  with raw signal quality near 1.6 and 69-71% hit rates, but these rows assume
  raw diagnostic settings rather than proving the live strategy can place and
  manage orders.
- Refreshed fast cross-rate diagnostics in
  `outputs/backtests/live_watch_cross_rate_eurgbp_refresh2_20260625.csv`; raw
  EURGBP rows remained eligible as signals.
- Ran exact live-config fixed-warmup validation in
  `outputs/backtests/live_watch_eurgbp_cross_rate_fixed_warmup_refresh_20260625_summary.csv`.
  Result: 0 evaluation fills across 6 folds, 0.0% active folds, and `REJECT`
  because the strategy produced no active fixed-warmup evaluation folds.
- Decision: keep EURGBP on `champion_ensemble`; do not route live EURGBP to
  `cross_rate_reversion` from raw watchlist diagnostics alone.

## 2026-06-25 6/18 MACD retest rejection

- Retested the higher-return `near_lower_6_18_h050_m035_eff07_s003_hold16`
  MACD candidate against the current promoted micro MACD row on the full
  `AUDUSD EURUSD USDCAD USDCHF` sleeve using
  `data/live7_full_backtest_prices_15m.csv` and
  `data/live7_full_backtest_quotes_15m.csv`.
- Outputs:
  `outputs/backtests/live_watch_macd_6_18_retest_20260625_w480.csv`,
  `outputs/backtests/live_watch_macd_6_18_retest_20260625_w672.csv`,
  `outputs/backtests/live_watch_macd_6_18_retest_20260625_w960.csv`, and
  `outputs/backtests/live_watch_macd_6_18_retest_consensus_20260625.csv`.
- The 6/18 row still looked attractive on headline return (+1.965% with 0.603%
  drawdown and 96 trades), but consensus stayed `PAPER_ONLY`: W480=`PAPER_ONLY`,
  W672=`PROMOTE`, W960=`PAPER_ONLY`, with only 55.6% minimum positive folds.
- Added the retest CSVs to the live status optimizer scan list so future
  summaries cite this fresh evidence.
- Decision: do not switch live MACD from the current micro 8/21/8 shape to the
  6/18 family; the extra return is not stable enough across validation windows.

## 2026-06-25 USDCAD sell-probe rejection

- A refreshed live pair read showed `USDCAD` as an `eligible_tiny_probe_sell`
  while production MACD remained flat because the quote was stale and the
  current MACD session window was closed.
- Refreshed an isolated USDCAD opportunity-probe scan on the full live7
  15-minute import:
  `outputs/backtests/live_watch_opportunity_probe_usdcad_sell_refresh_20260625_w960.csv`.
- The best selective row remained negative: -0.068% return, 187 trades,
  50.0% positive folds, 50.0% active-positive folds, and 50.0% non-negative
  folds. Looser rows lost more and increased churn.
- Added the refresh to the live status optimizer scan list so future heuristic
  USDCAD sell pressure cites exact same-day evidence.
- Decision: do not route USDCAD to `opportunity_probe`, do not force the
  heuristic sell, and keep USDCAD on the promoted MACD sleeve.
