# QuantHack — Improvement Pass (quanthackclaude)

This fork (`quanthackclaude`) is a copy of `quanthack` with a focused set of
improvements applied from the architecture review, prioritized around the
**published competition scoring formula** and verified against the test suite.

```
Final Score = 70% Return + 15% Drawdown + 10% Sharpe + 5% Risk Discipline
```

scored **per round**, with **forced liquidation @ 30% margin level = immediate
elimination** (a binary red-line rule). That shapes the whole strategy: earn a
competitive return each round while keeping a wide safety margin from both the
stop-out *and* the risk-discipline thresholds (leverage >28x, margin usage >90%,
single-instrument >90%, net-directional >95%).

**Test status:** baseline 502 tests → **509 tests, all passing** (7 added). All
changes are additive and backward-compatible; default behavior is unchanged
unless the new controls are explicitly enabled.

Run the suite:
```bash
PYTHONPATH=src python3.11 -m unittest discover -s tests
```

---

## 1. Risk engine — competition survival (`src/quanthack/trading/risk.py`)

Forced liquidation is fatal, so this got the most attention. All new fields
default to off; the engine behaves exactly as before unless configured.

- **`RiskLimits.competition_safe()`** — a documented preset that maps directly to
  the rulebook: moderate gross leverage (6x, far below the 28x risk-discipline
  line and the 30x ceiling), margin floors far above the 30% stop-out, a
  reduce-only margin tier, and a drawdown brake.
- **Graduated margin response** — new `reduce_only_margin_level_pct` puts the
  engine into `REDUCE_ONLY` on a transient margin dip instead of permanently
  `FROZEN`, so one bad tick doesn't forfeit the round's return (70% of score).
- **Drawdown brake** — `drawdown_derisk_start_pct` / `drawdown_derisk_full_pct`
  linearly scale new position size from 1.0 → 0.0 as drawdown rises between the
  two thresholds. This smooths the 15-minute equity curve (helps **Sharpe rank**)
  and caps MaxDD (helps **Drawdown rank**) *before* the hard reduce-only cliff.
- **`freeze_on_daily_loss` toggle** — lets the daily-loss stop downgrade to
  `REDUCE_ONLY` instead of `FROZEN`.
- **`STOP_OUT_MARGIN_LEVEL_PCT = 30.0`** constant documents the elimination line.
- **Validation** in `__post_init__` (reduce-only floor must exceed the freeze
  floor; derisk thresholds ordered and set together).

New tests: `tests/test_risk.py::CompetitionRiskControlsTest` (5 cases).

## 2. Metric correctness (`src/quanthack/backtesting/metrics.py`)

- **Profit factor no longer returns `+inf`** — capped at a finite
  `MAX_PROFIT_FACTOR` sentinel so it survives ranking and CSV/JSON
  serialization (it previously broke both).
- **`positive_period_rate`** added alongside `win_rate`. `win_rate` excludes flat
  periods (flatters low-activity strategies); the new metric counts all periods,
  giving an honest read. Added to `PerformanceMetrics` with a default so existing
  construction/serialization is unaffected.
- Sharpe was **left as-is on purpose**: it already uses population std
  (`pstdev`), which matches the competition's `Std` definition. (The review's
  "sample-std bias" note was mistaken.)

Updated/added tests in `tests/test_metrics.py`.

## 3. Config-aware status & symbol validation

- **`build_status(...)`** (`core/status.py`) now derives its fields from
  arguments instead of hard-coded literals, and derives `dry_run` from the route
  so they can't disagree. Defaults preserve the old output.
- **`AppConfig.validate_symbols()`** (`core/config.py`) — opt-in check that every
  strategy config's `symbol` exists in the instrument registry, so typos fail at
  startup/preflight rather than at first trade. Not auto-called, so it can't
  break an otherwise-usable config.

## 4. Competition config profile (`configs/competition.toml`)

A complete, ready-to-load config tuned toward the scoring formula:
`active = "champion_ensemble"` (the documented strongest single-strategy
candidate), the `competition_safe()` risk block (6x cap, 20% per-symbol cap,
150%/250% margin floors, 4%→10% drawdown brake), verified to load, validate
symbols, and build its strategy.

## 5. Tooling & CI

- `pyproject.toml`: added `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`
  and a `dev` extra (`ruff`, `mypy`, `pytest`).
- `.github/workflows/ci.yml`: installs the package, runs ruff + mypy (advisory)
  and the full test suite on push/PR.

---

## Honest caveats & recommended next steps

- **Alpha is not validated here.** The bundled sample data is synthetic, so the
  *machinery* and *risk posture* are improved but the strategies' edge must be
  re-validated on the organizer's real historical data before going live. The
  leverage/sizing in `competition.toml` is a deliberately moderate choice, not a
  proven optimum — tune it with walk-forward on real data.
- **Bigger items left for a follow-up** (flagged in the review, higher blast
  radius): split the 11k-line `strategies/strategy.py` monolith (extract
  AlphaRouter, CrossRateReversion, and a shared `signals.py`); add per-position
  cost-basis tracking + an explicit per-position stop-loss; route the "allocated
  exit" path through the risk engine; constrain the meta-layer parameter surface
  to fight overfitting (ML alpha already failed its own walk-forward).
- **Validation workflow to run on real data:**
  `quanthack-portfolio-walk-forward` and `quanthack-adaptive-strategy-select`,
  then promote only strategies that clear the documented out-of-sample gates.

---

## 6. Strategy research pass — see `RESEARCH_LOG.md`

A full autonomous build → backtest → OOS-validate cycle on the real 15-minute
dataset (`data/full_20gb_15m_*.csv`). Headline results (all verified, harnesses
in `outputs/research/`):

- **Root cause of weak returns: ~10–30x under-sizing.** Baseline used 0.53x of a
  6x allowance; Sharpe is leverage-invariant, so Return rank (70%) is unlocked by
  sizing up within the risk-discipline lines.
- **Robust signal family: low-turnover trend/momentum** (`macd_momentum`,
  `multi_horizon_momentum`, `quality_trend`, `volatility_squeeze`); high-turnover
  mean-reversion bleeds on costs.
- **Out-of-sample validated** (select on first 60%, test on last 40%): the
  best-trend-per-symbol map at the 0.80 sizing point returned **+1.44%** on
  held-out data, MaxDD 1.27%, **risk discipline 100/100**, 3.85x leverage.
- **Independently corroborated** by the project's own `portfolio-walk-forward`
  engine: `macd_momentum` diversified basket → **PROMOTE** (median test return
  1.19%, worst DD 0.76%, RD 100, 66.7% stable folds).
- **Locked in:** `configs/competition.toml` now carries the validated sizing;
  `outputs/research/run_competition_portfolio.sh` is the runnable recipe
  (full-data: +3.95% / MaxDD 1.96% / RD 100 / 5.28x leverage).
