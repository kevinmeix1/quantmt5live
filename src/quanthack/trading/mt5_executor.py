"""Live MetaTrader5 order executor.

Drop-in replacement for ``DryRunExecutor`` that places REAL market orders on an
MT5 account (the competition uses simulated funds but real order matching). It
matches the executor interface the live loop depends on (``current_portfolio``,
``submit``, ``journal_path``) so it slots straight into ``LiveDryRunEngine``.

Safety model (read this before going live):
  * ``live=False`` by default — the executor computes the intended order and
    journals it as ``MT5_SHADOW`` WITHOUT calling ``order_send``. You must pass
    ``live=True`` explicitly to place real orders.
  * Every order still passes the RiskEngine upstream (the loop only calls
    ``submit`` with an approved/blocked decision); blocked decisions never trade.
  * ``max_order_lots`` hard-caps the size of any single order as a last-resort
    backstop against a sizing bug.
  * Orders are reconciled against the LIVE MT5 position (delta-to-target), so a
    repeated target does not stack duplicate positions.

The MetaTrader5 package is Windows-only; it is imported lazily via the injected
market adapter's module, so this file imports fine (and is unit-tested with a
fake module) on any platform.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from quanthack.cli.manual_ticket import (
    DEFAULT_FX_CONTRACT_SIZE,
    _round_lots_down,
    _usd_notional_per_lot,
)
from quanthack.core.clock import UTC, CompetitionMode
from quanthack.core.instruments import AssetClass, instrument_for
from quanthack.trading.execution import ExecutionRecord, read_journal
from quanthack.trading.risk import (
    AccountSnapshot,
    PortfolioSnapshot,
    Position,
    RiskDecision,
    Side,
    TradeRequest,
)

EPSILON_LOTS = 1e-9


class MT5OrderError(RuntimeError):
    """Raised when a live MT5 order cannot be placed."""


@dataclass
class Mt5LiveExecutor:
    journal_path: Path
    market_adapter: object  # MT5MarketDataAdapter (has _module(), _mt5_symbol(), get_latest_quote())
    live: bool = False
    max_order_lots: float = 5.0
    volume_step: float = 0.01
    min_volume: float = 0.01
    deviation: int = 20
    magic: int = 20_260_621

    # --- portfolio (live positions -> signed USD notional) -------------------
    def current_portfolio(self) -> PortfolioSnapshot:
        mt5 = self.market_adapter._module()
        positions = mt5.positions_get()
        if not positions:
            return PortfolioSnapshot()
        by_symbol: dict[str, float] = {}
        for pos in positions:
            canonical = self._canonical_from_mt5(_attr(pos, "symbol"))
            if canonical is None:
                continue
            lots = float(_attr(pos, "volume"))
            is_buy = int(_attr(pos, "type")) == 0  # ORDER_TYPE_BUY == 0
            signed_lots = lots if is_buy else -lots
            by_symbol[canonical] = by_symbol.get(canonical, 0.0) + signed_lots * self._notional_per_lot(canonical)
        return PortfolioSnapshot(
            positions=tuple(
                Position(symbol=s, notional_usd=n)
                for s, n in sorted(by_symbol.items())
                if abs(n) > 0
            )
        )

    # --- order submission ----------------------------------------------------
    def submit(
        self,
        *,
        account: AccountSnapshot,
        request: TradeRequest,
        decision: RiskDecision,
        mode: CompetitionMode,
        portfolio_before: PortfolioSnapshot | None = None,
    ) -> ExecutionRecord:
        portfolio = portfolio_before or self.current_portfolio()
        if not decision.approved:
            return self._journal(account, request, decision, mode, portfolio,
                                  status="MT5_BLOCKED", note="risk blocked")

        # Target signed notional for this symbol -> target lots.
        target_signed = decision.adjusted_notional_usd * (1 if request.side == Side.BUY else -1)
        per_lot = self._notional_per_lot(request.symbol)
        target_lots = target_signed / per_lot
        current_lots = portfolio.notional_for_symbol(request.symbol) / per_lot
        delta_lots = target_lots - current_lots

        order_side = Side.BUY if delta_lots > 0 else Side.SELL
        trade_lots = _round_lots_down(min(abs(delta_lots), self.max_order_lots), self.volume_step)
        if trade_lots < self.min_volume - EPSILON_LOTS:
            return self._journal(account, request, decision, mode, portfolio,
                                  status="MT5_NO_CHANGE",
                                  note=f"delta {delta_lots:.4f} lots below min/step")

        if not self.live:
            return self._journal(account, request, decision, mode, portfolio,
                                 status="MT5_SHADOW",
                                 note=f"would {order_side.value} {trade_lots} lots (live disabled)")

        result = self._place_order(symbol=request.symbol, side=order_side, lots=trade_lots)
        status = "MT5_FILLED" if result.get("ok") else "MT5_ORDER_FAILED"
        return self._journal(account, request, decision, mode, portfolio,
                             status=status, note=json.dumps(result, sort_keys=True))

    # --- kill-switch: flatten everything immediately -------------------------
    def flatten_all(self, *, reason: str = "kill-switch") -> list[dict]:
        """Close ALL open positions right now (emergency de-risk / end-of-round
        protection). In shadow mode it reports what it would close.

        Returns one result dict per position; also journals a summary line.
        """
        mt5 = self.market_adapter._module()
        positions = mt5.positions_get() or ()
        results: list[dict] = []
        for pos in positions:
            mt5_symbol = str(_attr(pos, "symbol"))
            lots = float(_attr(pos, "volume"))
            is_buy = int(_attr(pos, "type")) == 0
            close_side = Side.SELL if is_buy else Side.BUY
            ticket = _attr(pos, "ticket", default=None)
            if not self.live:
                results.append({"ok": True, "shadow": True, "symbol": mt5_symbol,
                                "close_side": close_side.value, "lots": lots})
                continue
            results.append(self._send_market(
                mt5_symbol=mt5_symbol, side=close_side, lots=lots, position_ticket=ticket
            ))
        self._journal_event(status="MT5_FLATTEN",
                            note=json.dumps({"reason": reason, "results": results}, sort_keys=True))
        return results

    # --- order placement (real MT5) ------------------------------------------
    def _place_order(self, *, symbol: str, side: Side, lots: float) -> dict:
        mt5_symbol = self.market_adapter._mt5_symbol(instrument_for(symbol).symbol)
        return self._send_market(mt5_symbol=mt5_symbol, side=side, lots=lots)

    def _send_market(self, *, mt5_symbol: str, side: Side, lots: float,
                     position_ticket=None) -> dict:
        mt5 = self.market_adapter._module()
        tick = mt5.symbol_info_tick(mt5_symbol)
        if tick is None:
            raise MT5OrderError(f"no tick for {mt5_symbol}")
        price = float(_attr(tick, "ask")) if side == Side.BUY else float(_attr(tick, "bid"))
        order_type = mt5.ORDER_TYPE_BUY if side == Side.BUY else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": float(lots),
            "type": order_type,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "quanthack-live",
            "type_time": getattr(mt5, "ORDER_TIME_GTC", 0),
            "type_filling": getattr(mt5, "ORDER_FILLING_IOC", 1),
        }
        if position_ticket is not None:
            req["position"] = position_ticket  # close-by-ticket when flattening
        res = mt5.order_send(req)
        retcode = _attr(res, "retcode", default=None)
        ok = retcode == getattr(mt5, "TRADE_RETCODE_DONE", 10009)
        return {
            "ok": bool(ok),
            "retcode": retcode,
            "symbol": mt5_symbol,
            "side": side.value,
            "lots": float(lots),
            "price": price,
            "comment": str(_attr(res, "comment", default="")),
        }

    # --- helpers -------------------------------------------------------------
    def _notional_per_lot(self, symbol: str) -> float:
        instrument = instrument_for(symbol)
        mt5 = self.market_adapter._module()
        mt5_symbol = self.market_adapter._mt5_symbol(instrument.symbol)
        info = mt5.symbol_info(mt5_symbol)
        contract_size = float(_attr(info, "trade_contract_size", default=0.0)) or (
            DEFAULT_FX_CONTRACT_SIZE if instrument.asset_class == AssetClass.FOREX else 0.0
        )
        if contract_size <= 0:
            raise MT5OrderError(f"no contract size for {mt5_symbol}; set it explicitly")
        price = self.market_adapter.get_latest_quote(instrument.symbol).mid
        quote_usd_rate = None
        if instrument.quote_currency != "USD" and instrument.base_currency != "USD":
            quote_usd_rate = self.market_adapter.get_latest_quote(
                f"{instrument.quote_currency}USD"
            ).mid
        per_lot, _ = _usd_notional_per_lot(
            symbol=instrument.symbol,
            base_currency=instrument.base_currency,
            quote_currency=instrument.quote_currency,
            price=price,
            contract_size=contract_size,
            quote_usd_rate=quote_usd_rate,
        )
        return per_lot

    def _canonical_from_mt5(self, mt5_symbol: str) -> str | None:
        try:
            return instrument_for(mt5_symbol).symbol
        except KeyError:
            # try stripping a broker suffix like EURUSD.pro
            base = str(mt5_symbol).split(".")[0]
            try:
                return instrument_for(base).symbol
            except KeyError:
                return None

    def _journal(self, account, request, decision, mode, portfolio, *, status, note) -> ExecutionRecord:
        record = ExecutionRecord(
            record_id=f"mt5-{uuid4().hex}",
            created_at_utc=datetime.now(tz=UTC),
            mode=mode,
            account=account,
            request=request,
            decision=decision,
            status=status,
            portfolio_before=portfolio,
            platform="mt5_live" if self.live else "mt5_shadow",
        )
        self._write({**record.to_json_dict(), "note": note})
        return record

    def _journal_event(self, *, status: str, note: str) -> None:
        self._write({
            "record_id": f"mt5evt-{uuid4().hex}",
            "created_at_utc": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "status": status,
            "platform": "mt5_live" if self.live else "mt5_shadow",
            "note": note,
        })

    def _write(self, data: dict) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True) + "\n")


def _attr(obj, name, default="__raise__"):
    """Read an attribute from an MT5 namedtuple-ish object or a dict."""
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
    elif hasattr(obj, name):
        return getattr(obj, name)
    if default == "__raise__":
        raise MT5OrderError(f"missing field {name!r} on MT5 object")
    return default
