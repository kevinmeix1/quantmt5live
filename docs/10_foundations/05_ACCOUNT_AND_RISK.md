# Account And Risk Model

Step 5 adds the first risk model.

There is still no broker, no MT5, no API, and no live paper order. This step only
answers one question:

> If a strategy wanted to trade, would our safety rules approve, shrink, or block it?

## New Concepts

### Account Snapshot

An `AccountSnapshot` is a simple picture of the account:

- Current equity.
- Starting equity.
- Equity at the start of the day.
- Peak equity so far.
- Margin level, if the platform provides it.

From those values, the code calculates:

- Total P&L percentage.
- Daily P&L percentage.
- Drawdown percentage.

### Trade Request

A `TradeRequest` is not an order.

It is only a proposed action:

```text
BUY EURUSD with 50,000 USD notional because ...
```

Later, strategies will create trade requests. The risk engine will decide whether
they are allowed.

### Risk Decision

The risk engine returns a `RiskDecision`:

- Approved or blocked.
- Reason.
- Adjusted notional.
- Risk state.

## Starting Safety Defaults

These are deliberately conservative:

- Max gross leverage: `2.0x`
- Max single-symbol notional: `25%` of equity
- Max daily loss: `2.5%`
- Max drawdown: `6%`
- Checkpoint risk multiplier: `50%`
- Minimum internal margin level: `300%`

The official elimination threshold is more dangerous than our internal threshold.
We want the code to stop before the cliff.

## Run In VS Code Terminal

Make sure your prompt shows `(.venv)`, then run:

```bash
python scripts/dry_run/risk_demo.py
python scripts/dry_run/risk_demo.py --target-notional 900000
python scripts/dry_run/risk_demo.py --equity 974000 --day-start-equity 1000000
python -m unittest discover -s tests
```

Expected behavior:

- The normal demo should approve.
- The large notional demo should approve but shrink the notional.
- The daily-loss demo should block.
- The tests should end with `OK`.

## Why We Built This Before Strategy

A strategy is allowed to be wrong.

The risk engine is not allowed to be casual.

That is the whole architecture: strategy proposes, risk decides, execution obeys.

