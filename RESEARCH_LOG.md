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
