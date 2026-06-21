# Autocorrelation Regime

`autocorrelation_regime` is a research-only strategy for FX, metals, and crypto.

The idea:

```text
If recent returns are positively autocorrelated, follow the recent move.
If recent returns are negatively autocorrelated and price is stretched, fade it.
Stay flat when the regime is weak or the estimated edge is below cost.
```

Why it exists:

```text
FX can alternate between short bursts of continuation and noisy mean reversion.
This strategy tries to detect that from recent serial correlation instead of
always assuming momentum or always assuming reversion.
```

Current default:

```text
lookback: 32 bars
signal_lookback: 6 returns
minimum absolute autocorrelation: 0.18
minimum momentum move: 4.0 bps
minimum reversion z-score: 0.80
minimum expected edge: 3.0 bps
FX/metals UTC hours: 10-17
position sizing: volatility
```

## Evidence

First seven-symbol comparison:

```text
symbols: XAGUSD, XAUUSD, USDCHF, AUDUSD, GBPUSD, EURUSD, EURGBP
return: -0.476%
max drawdown: 0.574%
Sharpe 15m: -0.045
trades: 508
risk discipline: 100/100
verdict: REJECT
```

Stricter parameter probes reduced churn but did not create positive edge:

```text
strict_r30_m8_z12_edge5: -0.057%, 74 trades
strict_r40_m10_z15_edge6: -0.038%, 12 trades
momentum_only_r35: -0.042%, 8 trades
reversion_only_r35: -0.003%, 26 trades
```

Asset split:

```text
metals only: -0.018%, 20 trades
FX subset: -0.188%, 316 trades
```

Verdict:

```text
Keep the implementation as a research diagnostic. Do not add it to champion
ensemble, adaptive selection, or live MT5 routing unless later data overturns
this rejection.
```

## Commands

Initial comparison:

```bash
quanthack portfolio-compare \
  --strategy autocorrelation_regime \
  --strategy macd_momentum \
  --strategy champion_ensemble \
  --strategy kalman_trend \
  --symbol XAGUSD --symbol XAUUSD --symbol USDCHF --symbol AUDUSD \
  --symbol GBPUSD --symbol EURUSD --symbol EURGBP \
  --price-csv data/full_20gb_15m_prices.csv \
  --quote-csv data/full_20gb_15m_quotes.csv \
  --output outputs/backtests/autocorrelation_regime_initial_compare.csv
```
