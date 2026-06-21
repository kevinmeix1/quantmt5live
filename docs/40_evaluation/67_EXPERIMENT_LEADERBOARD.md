# Experiment Leaderboard

`experiment-leaderboard` ranks walk-forward summary CSVs from
`outputs/backtests`.

Why it exists:

```text
Strategy research now produces many CSVs.
The leaderboard gives one quick view of which experiments are cleanest by
positive folds, active-positive folds, non-negative folds, drawdown, median
active return, fills, and risk discipline.
```

Command:

```bash
quanthack experiment-leaderboard \
  --input 'outputs/backtests/*summary.csv' \
  --output outputs/backtests/experiment_leaderboard.csv \
  --limit 20
```

Latest read:

```text
The conservative MACD basket ranks as the cleanest validation profile.
The seven-symbol adaptive candidate remains the stronger broader paper candidate.
Rejected add-ons such as USD pressure, broad multi-horizon momentum, and session
breakout do not improve the main candidate.
```

Use this before changing defaults. If an experiment does not beat the current
leaderboard profile on both return quality and fold stability, keep it as a
research sleeve instead of promoting it.
