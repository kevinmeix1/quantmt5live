# Adaptive Strategy Selection

`adaptive-strategy-select` is a walk-forward research tool for choosing between
complete portfolio strategies.

The question it answers:

```text
If we only knew the previous training window, which strategy would we have run
for the next unseen window?
```

This is different from `strategy-map-optimize`:

- `strategy-map-optimize` searches symbol -> strategy assignments.
- `adaptive-strategy-select` searches strategy -> time-window assignments.
- `adaptive-strategy-select --candidate-map` can also compare complete
  deployable maps as time-window candidates.
- `adaptive-strategy-select --recipe-map` can compare deployable maps with
  different symbol universes.

## Method

For each fold:

1. Slice a training window.
2. Backtest each candidate strategy on that training window.
3. Rank strategies by risk discipline, activity, drawdown-adjusted return,
   Sharpe, raw return, and drawdown.
4. Optionally apply training gates such as minimum train fills or minimum
   drawdown-adjusted train return.
5. Select the best recent eligible strategy.
6. Replay the selected strategy over train + test history.
7. Score only the test window.

The train window is used as warmup for indicators and positions, but only the
next test window is counted as out-of-sample evidence.

## Command

```bash
quanthack adaptive-strategy-select \
  --strategy kalman_trend \
  --strategy champion_ensemble \
  --strategy macd_momentum \
  --symbol XAGUSD --symbol XAUUSD --symbol USDCHF --symbol AUDUSD \
  --symbol GBPUSD --symbol EURUSD --symbol EURGBP \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --train-size 480 \
  --test-size 96 \
  --step-size 96 \
  --force-qualify-mode \
  --loss-cooldown-folds 1 \
  --summary-output outputs/backtests/adaptive_strategy_selection_summary.csv \
  --folds-output outputs/backtests/adaptive_strategy_selection_folds.csv \
  --scores-output outputs/backtests/adaptive_strategy_selection_scores.csv \
  --stitched-equity-output outputs/backtests/adaptive_strategy_selection_stitched_equity.csv \
  --promotion-output outputs/backtests/adaptive_strategy_selection_promotion.csv
```

Use `--force-qualify-mode` for historical full-data research during a live
competition. Without it, the competition clock can correctly classify older
historical bars as non-QUALIFY and produce no active folds.

## How To Read It

Use the summary CSV first:

```text
positive_fold_fraction
active_positive_fold_fraction
non_negative_fold_fraction
median_active_test_return_pct
worst_test_drawdown_pct
selection_counts
```

Then inspect the folds CSV:

```text
selected_strategy
selected_train_return_pct
selected_train_drawdown_adjusted_return_pct
return_pct
max_drawdown_pct
risk_discipline_score
```

The scores CSV shows every candidate strategy's training score in every fold,
which helps explain why the selector picked a strategy.

Optional training gates:

```text
--min-train-fills N
--min-train-adjusted-return-pct X
--train-fill-penalty-pct X
```

These gates prevent a candidate from being selected when its training run is too
thin or too weak. If every candidate fails the gates, the selector falls back to
the best raw training score so a fold is still evaluated. The folds CSV records
`train_gate_blocked_strategies`, and the scores CSV records `train_gate_passed`.

`--train-fill-penalty-pct` is a softer churn guardrail. It subtracts a small
decimal return amount for every training-window fill before ranking candidates:

```text
training score = return - drawdown penalty - (fills * fill penalty)
```

On the current seven-symbol `kalman_trend / champion_ensemble / macd_momentum`
candidate, penalties from `0.000001` through `0.00002` did not change selection
counts or out-of-sample metrics. Verdict: keep it as a robustness probe; do not
enable it by default because it currently adds no improvement.

For `--candidate-map`, the label is what appears as the candidate name, and the
score CSV includes a `strategy_map` column with the exact symbol recipe.

Use `--recipe-map` when a candidate should trade only the symbols listed in the
recipe. This is useful for comparing a conservative basket against a broader
candidate without forcing every strategy to run on every symbol.

The stitched equity CSV compounds test-window returns into a single
out-of-sample research curve. It is useful for the dashboard and demo, but it is
not a claim that positions were carried continuously across folds.

The promotion audit CSV lists each research/live gate separately. Use it to see
exactly why a run is `REJECT`, `PAPER_ONLY`, or `PROMOTE`.

## Promotion Rule Of Thumb

Treat adaptive selection as paper research until it beats the simple baseline
strategy in walk-forward validation.

Good signs:

```text
active positive folds >= 60%
non-negative folds >= 75%
median active return > 0
risk discipline near 100/100
selection counts are not dominated by one lucky fold
```

Bad signs:

```text
full-sample return improves but walk-forward median active return worsens
selector keeps chasing the previous fold's winner and then loses
one strategy is always selected and the tool adds no value
```

## Current Finding

Seven-symbol run:

```text
symbols:
  XAGUSD, XAUUSD, USDCHF, AUDUSD, GBPUSD, EURUSD, EURGBP

candidate strategies:
  kalman_trend, champion_ensemble, macd_momentum

folds:
  17
```

Best current result with session-filtered MACD and one-fold loss cooldown:

```text
command option: --loss-cooldown-folds 1
positive fold fraction: 47.1%
active fold fraction: 64.7%
active positive fold fraction: 72.7%
non-negative fold fraction: 82.4%
median active test return: 0.033%
worst test drawdown: 0.071%
risk discipline: 100/100
evaluation fills: 86
stitched OOS final equity: $1,004,225.57
selection counts: kalman_trend=2, champion_ensemble=5, macd_momentum=10
promotion: PAPER_ONLY
```

No-cooldown result with session-filtered MACD:

```text
--loss-cooldown-folds 0:
  positive fold fraction: 41.2%
  active positive folds: 63.6%
  non-negative folds: 76.5%
  median active return: 0.033%
  worst drawdown: 0.071%
  promotion: PAPER_ONLY
```

Earlier cooldown check before the MACD session filter:

```text
One-fold cooldown was only a tiny improvement before session filtering.
Two-fold cooldown was too blunt and rejected.
```

Fair fixed-strategy comparison on the same folds:

```text
fixed kalman_trend:
  active positive folds: 55.6%
  non-negative folds: 76.5%
  median active return: 0.003%

fixed champion_ensemble:
  active positive folds: 44.4%
  non-negative folds: 70.6%
  median active return: -0.000%

fixed macd_momentum:
  active positive folds: 60.0%
  non-negative folds: 76.5%
  median active return: 0.017%
```

Verdict:

```text
Adaptive selection with session-filtered MACD and one-fold cooldown is the best
current paper candidate. It passes active-positive and non-negative validation
quality, but remains paper-only because total positive folds are below the
stricter 67% live gate.
```

Broad strategy-set scan:

```text
Adding dual_squeeze, asset_adaptive_dual_squeeze, fixing_reversal, and
trend_pullback worsened validation:

active positive folds: 25.0%
non-negative folds: 64.7%
median active return: -0.020%
```

Interpretation:

```text
The adaptive layer should use a small candidate set with prior evidence.
Adding many weaker sleeves makes the selector overfit the latest training
window.
```

Recent rejected alpha sleeves:

```text
session_momentum:
  best optimized default had positive full-sample return but weak walk-forward
  median active return. Keep as research infrastructure only.

intraday_seasonality:
  same-time-of-day momentum and reversal were both too noisy on the current
  seven-symbol sample. The adaptive selector naturally ignored it when included.
```

## Candidate Map Check

The selector can now compare static maps as first-class candidates:

```bash
quanthack adaptive-strategy-select \
  --strategy kalman_trend \
  --strategy champion_ensemble \
  --strategy macd_momentum \
  --candidate-map 'top5_static_map:XAGUSD=champion_ensemble,XAUUSD=macd_momentum,AUDUSD=macd_momentum,USDCHF=macd_momentum,EURUSD=macd_momentum' \
  --symbol XAGUSD --symbol XAUUSD --symbol AUDUSD --symbol USDCHF --symbol EURUSD \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --train-size 480 \
  --test-size 96 \
  --step-size 96 \
  --loss-cooldown-folds 1 \
  --summary-output outputs/backtests/adaptive_candidate_map_top5_summary.csv \
  --folds-output outputs/backtests/adaptive_candidate_map_top5_folds.csv \
  --scores-output outputs/backtests/adaptive_candidate_map_top5_scores.csv \
  --stitched-equity-output outputs/backtests/adaptive_candidate_map_top5_equity.csv
```

Five-symbol result:

```text
candidates:
  kalman_trend, champion_ensemble, macd_momentum, top5_static_map

selection counts:
  kalman_trend=1
  champion_ensemble=5
  macd_momentum=8
  top5_static_map=3

active positive folds: 62.5%
non-negative folds: 82.4%
median active return: 0.029%
worst drawdown: 0.075%
stitched OOS final equity: $1,003,637.00
promotion: PAPER_ONLY
```

Interpretation:

```text
Candidate-map selection is useful and deployable, but this five-symbol map run
does not beat the seven-symbol adaptive selector with session-filtered MACD.
Keep it as backup evidence, not the top candidate.
```

## Recipe Map Check

Recipe maps allow partial symbol universes:

```bash
quanthack adaptive-strategy-select \
  --no-default-strategies \
  --recipe-map 'conservative_macd:AUDUSD=macd_momentum,EURCHF=macd_momentum,EURUSD=macd_momentum,USDCAD=macd_momentum,USDJPY=macd_momentum,XAGUSD=macd_momentum,XAUUSD=macd_momentum' \
  --recipe-map 'top5_static_map:XAGUSD=champion_ensemble,XAUUSD=macd_momentum,AUDUSD=macd_momentum,USDCHF=macd_momentum,EURUSD=macd_momentum' \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --train-size 480 \
  --test-size 96 \
  --step-size 96 \
  --loss-cooldown-folds 1
```

Latest recipe-selector run:

```text
candidates:
  conservative_macd
  top5_static_map
  current7_macd
  xag_champion_scan_macd

positive folds: 29.4%
active positive folds: 55.6%
non-negative folds: 76.5%
median active return: 0.013%
stitched OOS final equity: $1,004,169.77
promotion: PAPER_ONLY
```

Interpretation:

```text
The feature is useful for fair static-recipe comparisons, but this recipe mix
does not beat the current top adaptive candidate.
```

## Training Gate Check

Training gates were added after recipe experiments over-selected sparse
candidates such as `multi_horizon_top3`.

Two checks were run:

```text
main plus clean recipes, min_train_fills=12:
  stitched OOS final equity: $1,002,768.91
  active positive folds: 55.6%
  non-negative folds: 76.5%
  median active return: 0.003%

main seven-symbol adaptive, min_train_adjusted_return=0.0:
  stitched OOS final equity: $1,003,914.26
  active positive folds: 63.6%
  non-negative folds: 76.5%
  median active return: 0.033%
```

Interpretation:

```text
Training gates are useful diagnostics and may prevent obvious sparse-candidate
mistakes, but they do not beat the current ungated one-fold-cooldown adaptive
candidate on this data.
```

## Per-Symbol Adaptive Check

`--per-symbol-selection` adds a dynamic candidate named `per_symbol_adaptive`.
For each fold it scores the recent training window separately for each symbol
and builds a deployable map such as:

```text
XAGUSD=kalman_trend XAUUSD=kalman_trend USDCHF=macd_momentum ...
```

Use `--per-symbol-only` to force that dynamic map every fold:

```bash
quanthack adaptive-strategy-select \
  --strategy kalman_trend \
  --strategy champion_ensemble \
  --strategy macd_momentum \
  --per-symbol-selection \
  --per-symbol-only \
  --symbol XAGUSD --symbol XAUUSD --symbol USDCHF --symbol AUDUSD \
  --symbol GBPUSD --symbol EURUSD --symbol EURGBP \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --train-size 480 \
  --test-size 96 \
  --step-size 96 \
  --loss-cooldown-folds 1
```

Latest forced dynamic-map run:

```text
positive folds: 29.4%
active positive folds: 55.6%
non-negative folds: 76.5%
median active return: 0.003%
worst drawdown: 0.106%
stitched OOS final equity: $1,003,938.32
promotion: PAPER_ONLY
```

Interpretation:

```text
Per-symbol selection is useful diagnostics, but the forced dynamic map did not
beat the current global adaptive selector. Keep it out of the main candidate
until it improves active-positive folds and drawdown.
```
