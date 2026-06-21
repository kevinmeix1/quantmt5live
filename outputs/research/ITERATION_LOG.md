# Autonomous Iteration Log

Persistent state for the scheduled research loop. Each wake-up: pick the next
`[ ]` task, run it, append results, check the box, schedule the next wake.
Guardrails every iteration: keep the 509-test suite green; never claim alpha
without an out-of-sample / cost-stress check; log honest negative results too.

## Backlog (queue)
- [x] 1. Cost-stress robustness — does the validated edge survive 2x/3x/5x fill slippage?
- [x] 2. Per-round simulation — reset equity per daily round (22:00 cuts), measure per-round return/DD/Sharpe (mirrors actual scoring).  ** KEY FINDING — see below **
- [x] 8. Per-round CONSISTENCY — tested regime diversification, trimming, adaptive strategies. ROOT-CAUSED (see iter 5): ceiling is structural cross-asset correlation; unlock needs crypto / uncorrelated signals.
- [ ] 9. Crypto readiness — verify pipeline trades crypto end-to-end; THE real decorrelator (24/7, fills flat FX rounds). Blocked on real crypto data; prototype only.
- [ ] 3. Sharpe improvement — diagnose & reduce the low 15m Sharpe (idle-bar variance / churn).
- [ ] 4. Crypto coverage — no crypto in bundled data; generate synthetic crypto series & test trend strategies (competition has 5 crypto).
- [ ] 5. Drawdown-brake stress — construct an adverse sub-window, confirm the coded brake cuts MaxDD.
- [ ] 6. Regime stability — sub-window-by-sub-window performance of the recommended map.
- [ ] 7. Sizing re-tune via project walk-forward across more strategies/baskets.
- [x] C1. Code efficiency — profile the backtest hot loop, optimize the top hotspot (tests must stay green + identical results).
- [x] C2/efficiency. instrument_for() O(1) dict lookup (was linear scan, called per-bar in router/ensemble paths).
- [ ] C3. Code quality — run ruff/mypy (dev extra), fix high-confidence findings without behavior change.
- [x] W1. Winning-areas audit — overfitting (cross-dataset), tail/gap risk, deployment robustness, rank-vs-field. See iter 6.
- [ ] W2. Round-staged risk posture — survive R1-R3, escalate in finals; wire FINAL_RANK_PUSH to sizing (currently only CHECKPOINT_PROTECT de-risks).
- [ ] W3. Drawdown/Sharpe RANK play — quantify how a low-vol book ranks vs a high-vol gambler field (needs field assumptions).

## Results

### Iteration 1 — Cost-stress robustness (harness: `cost_stress.py`)
Recommended trend map, scaling realized fill slippage only:

| slippage | return | MaxDD | Sharpe | RD |
|---|---|---|---|---|
| 1 bps | +3.95% | 1.96% | 0.022 | 100 |
| 2 bps | +2.71% | 2.14% | 0.015 | 100 |
| 3 bps | +1.48% | 2.33% | 0.008 | 100 |
| 5 bps | −0.96% | 4.24% | −0.005 | 100 |

**Verdict:** edge is real but moderately cost-sensitive — breakeven ≈ 4 bps
slippage. Survives realistic 2–3 bps execution. **Actions for later iterations:**
favor lowest-turnover trend strategies; lean toward tight-spread FX majors;
re-examine the higher-turnover symbols (XAGUSD session/macd had 50–110 fills).
Risk discipline stayed 100/100 throughout.

### Iteration 2 — Code efficiency (profile-guided)
Profiled a full portfolio backtest (cProfile): hot path is per-bar strategy
evaluation; `read_kalman_regime` and the shared `_recent_valid_prices` helper
dominate. Found a real inefficiency in `strategies/strategy.py::_recent_valid_prices`:
`list(prices)[-lookback:]` copied the **entire growing price history** each call
(O(N)) before slicing. Fixed to `list(prices[-lookback:])` (O(lookback)).

- **Verification:** full recipe output byte-identical (+3.952% / 1.962% / 5.28x /
  RD 100); full suite still **509 passing**.
- **Benchmark:** 7.9x faster on the helper at 2200-bar history; the gap grows
  with history length, so the win is largest on the organizer's bigger datasets.
- Left `read_kalman_regime` untouched (numerical; incremental-state refactor too
  risky for an autonomous pass without a dedicated equivalence test). Queued as a
  candidate if a regression harness is added.

### Iteration 3 — Cost-aware re-selection (strategy) + instrument_for O(1) (code)
**Code:** `core/instruments.py::instrument_for` now uses a module-level dict for
O(1) lookup instead of a linear scan over DEFAULT_INSTRUMENTS (it's called
per-bar in router/ensemble paths). Verified: `test_instruments` + full suite
**509 green**; recipe byte-identical (+3.952% / 1.962%).

**Strategy (negative result — kept current recipe):** re-selected the per-symbol
map at a realistic 2 bps slippage with a 40-fills/month turnover cap. Changes
suggested: USDCHF→macd, XAUUSD→trend_pullback, XAGUSD→volatility_squeeze. Result:

| slippage | current ret/DD | cost-aware ret/DD | composite(0.70·ret−0.15·DD) |
|---|---|---|---|
| 2 bps | 2.714% / 2.143% | 1.445% / 0.929% | current 1.58 vs 0.87 |
| 3 bps | 1.484% / 2.334% | 0.869% / 1.111% | current 0.69 vs 0.44 |

The cost-aware map is more cost-robust and has a better return/DD *ratio*, but
under the actual 70/15 weighting its lower absolute return loses. **Decision:
keep the current recipe** — this validates it against the cost concern rather
than replacing it. (If competitor drawdowns turn out high, the low-DD variant
could rank better; revisit with real leaderboard data.)

### Iteration 4 — Per-round simulation (HEADLINE rules-faithful finding)
Harness: `per_round_sim.py`. Sliced the recommended-recipe equity curve into 24h
rounds at 22:00 cuts (how the competition actually scores & eliminates).

| metric | value |
|---|---|
| rounds | 24 |
| positive rounds | **8/24 (33%)** |
| mean / median round return | 0.165% / **0.000%** |
| worst round return | −0.943% |
| worst intra-round drawdown | **1.286%** (30% = forced-liquidation line) |
| mean round Sharpe | −0.007 (8/24 positive) |

**Interpretation (reframes the project):**
- The whole-month +3.95% is **concentrated in a single round** (2026-06-04,
  +3.55%). Aggregate return badly overstates per-round competitiveness.
- **Strength:** zero stop-out risk (worst round DD 1.3% vs 30% line) — this is a
  *survivor* in an elimination format where aggressive entrants get liquidated.
- **Weakness:** alpha is concentrated in rare trend days; per-round consistency
  is poor, so it relies on a big day landing before an early-round elimination.
- **Consistency is sizing-invariant** (sign of each round doesn't change with
  leverage), so the fix is signal/diversification, not sizing.

**Strategic conclusion:** optimize for *positive-round frequency / upper-half
ranking each round*, not aggregate return. New backlog task 8 added. Also: this
is the headline caveat to surface to the user — re-validate on the organizer's
real competition-window data, since round composition matters enormously.
(Analysis-only iteration; no code change; suite remains 509 green.)

### Iteration 5 — Acting on the recommendations (regime diversification etc.)
Tested the "improve consistency" recommendations directly. **All negative on
this data — kept the trend recipe.** Harness: `regime_diversify.py`.

Candidate portfolios by positive-round fraction (non-flat rounds):

| candidate | pos%(non-flat) | worst round | agg ret | agg DD |
|---|---|---|---|---|
| **trend_recipe (kept)** | **42%** | −0.94% | +3.95% | 1.96% |
| regime_split (+reversion) | 39% | −0.96% | +2.28% | 3.46% |
| champion (all) | 31% | −0.79% | +3.71% | 3.58% |
| regime_switch (all) | 31% | −2.62% | −5.28% | 7.89% |
| autocorr (all) | 18% | −1.99% | −5.03% | 5.51% |
| alpha_router (all) | 0% | −2.24% | −5.13% | 5.21% |

**Root cause (why diversification doesn't help):** the trend symbols have a
**0.58 mean pairwise round-return correlation** (range 0.36–0.83) — they're all
USD/macro-driven, so they co-move; adding more of them can't smooth per-round
PnL, and the available reversion/adaptive strategies have *negative* expectancy
here so mixing them in only dilutes the edge and raises drawdown.

**Trimming test:** dropping the two net-negative symbols (USDJPY −$1,059,
EURCHF −$66) gave only +0.10% return / −0.03% DD and **zero** consistency gain
(still 33% positive rounds) — marginal and in-sample, so not adopted.

**Conclusions:**
- On this instrument set + available signals, the trend recipe is at the
  efficient frontier; the recommendations don't beat it. Not shipping a worse
  or overfit config.
- The consistency/Sharpe ceiling is **structural correlation**. The only genuine
  unlocks are (a) **crypto** — an uncorrelated, 24/7 asset class that would fill
  the flat FX weekend rounds (no data yet → task 9, prototype-only), and
  (b) a genuinely uncorrelated *profitable* signal (research beyond this window).
- Highest-certainty real improvement remains: re-select/validate on the
  organizer's actual competition-window data.

### Iteration 6 — "What else is needed to WIN" audit + deployment hardening
Stepped back from backtest-return tunnel vision to the areas that actually
decide a rank-based, per-round-elimination contest.

1. **Overfitting (cross-dataset):** the other data files (downloaded_scan/
   portfolio/backtest) are the SAME source/window as the big set (2026-05-11 →,
   2-day subsets) — so true cross-dataset validation is impossible with what we
   have. **We have exactly one data window.** This is the dominant residual risk
   and is only resolvable on the organizer's real data.
2. **Tail/gap risk (tested):** worst 1h adverse move = XAGUSD 4.79% (silver is
   4–8x more volatile than the FX pairs; 262 bps single-bar). At the recipe's
   5.28x leverage even a fully-concentrated hit ≈ 25% equity vs the ~95% needed
   for the 30% stop-out → **huge safety margin; no elimination risk at current
   sizing.** Per-symbol volatility sizing already keeps metals right-sized (they
   are net-positive contributors). Caveat: metals become the binding tail risk
   if leverage is pushed up.
3. **Deployment robustness (FIXED + tested):** `live_dry_run.run()` had NO
   per-iteration error handling — one transient tick failure would crash the
   whole multi-day run → >8h inactivity = elimination. Added a resilient loop
   (`continue_on_error=True` default): failed ticks are recorded as
   `LiveDryRunError` and skipped, the loop keeps polling. +2 tests; suite now
   **511 green**.
4. **Rank-vs-field insight (analytical):** score is percentile vs the field, so a
   low-vol book can rank HIGH on Drawdown (15%) and Sharpe (10%) against a field
   of high-vol gamblers who self-eliminate via forced liquidation — the "weak"
   Sharpe may not be weak *in rank terms*. Reinforces the survivor thesis.

**New backlog:** W2 (round-staged aggression: escalate sizing in finals — only
CHECKPOINT_PROTECT currently changes risk), W3 (quantify the rank-vs-field play).
**Biggest remaining gaps to actually WIN:** (a) higher return without losing the
quality edge → needs the crypto/uncorrelated unlock; (b) a REAL executor +
reliable multi-day deployment (only paper/dry-run exists today).

