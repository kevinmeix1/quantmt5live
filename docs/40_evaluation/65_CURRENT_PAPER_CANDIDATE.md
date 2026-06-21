# Current Paper Candidate

This is the current best research profile from the imported 15-minute data.

## Top Candidate

Use adaptive strategy selection with:

```text
symbols:
  XAGUSD, XAUUSD, USDCHF, AUDUSD, GBPUSD, EURUSD, EURGBP

candidate strategies:
  kalman_trend
  champion_ensemble
  macd_momentum

MACD session filter:
  FX/metals 10-14 UTC

loss cooldown:
  1 fold
```

Latest validation:

```text
folds: 17
positive fold fraction: 47.1%
active fold fraction: 64.7%
active positive fold fraction: 72.7%
non-negative fold fraction: 82.4%
median active test return: 0.033%
worst test drawdown: 0.071%
risk discipline: 100/100
evaluation fills: 86
stitched OOS final equity: $1,004,225.57
promotion: PAPER_ONLY
blocking live gate: total positive folds 47.1% vs 67.0% required
```

This is not automatic-live ready yet because total positive folds are still
below the stricter 67% live gate. It is the strongest paper/dry-run candidate.

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
  --loss-cooldown-folds 1 \
  --summary-output outputs/backtests/adaptive_strategy_selection_session_macd_cooldown1_summary.csv \
  --folds-output outputs/backtests/adaptive_strategy_selection_session_macd_cooldown1_folds.csv \
  --scores-output outputs/backtests/adaptive_strategy_selection_session_macd_cooldown1_scores.csv \
  --stitched-equity-output outputs/backtests/adaptive_strategy_selection_session_macd_cooldown1_equity.csv \
  --promotion-output outputs/backtests/adaptive_strategy_selection_session_macd_cooldown1_promotion.csv
```

The stitched equity CSV is an out-of-sample research curve for the dashboard.
It compounds fold test-window returns into one curve, while still keeping fold
and selected-strategy columns for inspection.

The promotion audit CSV is the fastest way to explain the current paper-only
status in a demo or live-readiness review.

## Simpler Backup

If adaptive strategy selection feels too complex to operate, use the static
top-5 strategy map:

```text
XAGUSD=champion_ensemble
XAUUSD=macd_momentum
AUDUSD=macd_momentum
USDCHF=macd_momentum
EURUSD=macd_momentum
```

Validation:

```text
active positive folds: 62.5%
non-negative folds: 82.4%
median active return: 0.019%
max drawdown: 0.100%
risk discipline: 100/100
```

Command:

```bash
quanthack portfolio-fixed-warmup-walk-forward \
  --strategy champion_ensemble \
  --strategy-map XAUUSD=macd_momentum \
  --strategy-map AUDUSD=macd_momentum \
  --strategy-map USDCHF=macd_momentum \
  --strategy-map EURUSD=macd_momentum \
  --symbol XAGUSD --symbol XAUUSD --symbol AUDUSD --symbol USDCHF --symbol EURUSD \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --train-size 480 \
  --test-size 96 \
  --step-size 96
```

CSV live dry-run check:

```bash
quanthack live-dry-run \
  --adapter csv \
  --strategy champion_ensemble \
  --strategy-map XAUUSD=macd_momentum \
  --strategy-map AUDUSD=macd_momentum \
  --strategy-map USDCHF=macd_momentum \
  --strategy-map EURUSD=macd_momentum \
  --symbol XAGUSD --symbol XAUUSD --symbol AUDUSD --symbol USDCHF --symbol EURUSD \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --bars 120 \
  --iterations 1 \
  --journal outputs/top5_static_map_live_dry_run_journal.jsonl \
  --monitor-output outputs/top5_static_map_live_monitor.csv
```

This command is useful before MT5 work because it proves the live dry-run path
can run the same per-symbol strategy map used by the static backtest.

Adaptive map-selection check:

```text
The adaptive selector can now compare this static map as a whole candidate via
--candidate-map. On the five-symbol universe, it selected the map in 3 of 17
folds and produced:

active positive folds: 62.5%
non-negative folds: 82.4%
median active return: 0.029%
stitched OOS final equity: $1,003,637.00
promotion: PAPER_ONLY
```

That is solid backup evidence, but it does not beat the seven-symbol adaptive
candidate above.

## Conservative MACD Basket

A fresh universe scan found a clean MACD-only backup basket:

```text
AUDUSD
EURCHF
EURUSD
USDCAD
USDJPY
XAGUSD
XAUUSD
```

Fixed-warmup validation:

```text
positive fold fraction: 35.3%
active fold fraction: 41.2%
active positive fold fraction: 85.7%
non-negative fold fraction: 94.1%
median active return: 0.072%
worst drawdown: 0.052%
risk discipline: 100/100
evaluation fills: 62
promotion: PAPER_ONLY
```

This is more selective than the top adaptive candidate but cleaner when it
actually trades. Keep it as a conservative paper/live-dry-run comparison path.

Recipe-level adaptive selection can compare this basket against other static
recipes using `--recipe-map`. The first recipe-selection run reached stitched
OOS final equity of `$1,004,169.77`, close to the main adaptive candidate, but
with weaker active-positive validation:

```text
active positive folds: 55.6%
non-negative folds: 76.5%
median active return: 0.013%
promotion: PAPER_ONLY
```

So `--recipe-map` is useful infrastructure, but the main top candidate remains
the adaptive `kalman_trend / champion_ensemble / macd_momentum` run.

## Multi-Horizon Momentum Backup

`multi_horizon_momentum` was added as a volatility-managed trend sleeve. Broad
seven-symbol use was rejected, but symbol eligibility found a cleaner top-3
basket:

```text
AUDUSD
USDCHF
XAUUSD
```

Top-3 fixed-warmup validation:

```text
positive fold fraction: 35.3%
active fold fraction: 58.8%
active positive fold fraction: 60.0%
non-negative fold fraction: 82.4%
median active return: 0.009%
worst drawdown: 0.039%
risk discipline: 100/100
evaluation fills: 72
promotion: PAPER_ONLY
```

Adaptive recipe selection can compare this top-3 basket with the main
strategies:

```text
recipe: multi_horizon_top3
stitched OOS final equity: $1,003,145.74
active positive folds: 54.5%
non-negative folds: 76.5%
median active return: 0.013%
promotion: PAPER_ONLY
```

This is a useful research/paper backup, but it does not beat the main adaptive
candidate or the conservative MACD basket.

## Avoid For Now

```text
broad adaptive selector:
  too many weaker sleeves caused overfitting

loss cooldown = 2:
  over-corrected and rejected

naive best_per_symbol_all map:
  worsened active-fold validation

automatic live MT5 execution:
  wait until paper/live dry-run evidence is stronger

session_momentum and intraday_seasonality:
  useful research infrastructure, but rejected by latest walk-forward evidence

broad multi_horizon_momentum:
  positive full-sample, but seven-symbol walk-forward active median was negative

usd_pressure_router:
  selected twice in adaptive testing but lowered stitched equity and fold quality

relative_strength and cross_rate_reversion:
  adaptive selector ignored them, so they are not additive on this sample

session_breakout:
  symbol eligibility was negative across broad baskets, with only inactive sparse variants

main plus clean recipes:
  over-selected sparse recipes and did not beat the main seven-symbol adaptive run

adaptive training gates:
  useful diagnostics, but min_train_fills=12 and min_train_adjusted_return=0.0
  both trailed the ungated one-fold-cooldown main candidate
```
