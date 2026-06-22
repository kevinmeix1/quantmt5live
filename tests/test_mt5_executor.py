from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from quanthack.core.clock import UTC, CompetitionMode
from quanthack.market.market_data import QuoteSnapshot
from quanthack.trading.execution import read_journal
from quanthack.trading.mt5_executor import MT5OrderError, Mt5LiveExecutor
from quanthack.trading.risk import (
    AccountSnapshot,
    Position,
    PortfolioSnapshot,
    RiskDecision,
    RiskState,
    Side,
    TradeRequest,
)


class _FakeMT5:
    """Minimal fake of the MetaTrader5 module recording order_send calls."""

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2

    def __init__(self, positions=(), symbol_info=None):
        self.sent: list[dict] = []
        self._positions = positions
        self._symbol_info = symbol_info or SimpleNamespace(
            trade_contract_size=100_000.0,
            volume_min=0.01,
            volume_step=0.01,
            filling_mode=3,
        )

    def positions_get(self, *a, **k):
        return self._positions

    def symbol_info(self, symbol):
        return self._symbol_info

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.0999, ask=1.1001)

    def order_send(self, request):
        self.sent.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="done", order=1)

    def last_error(self):
        return (1, "fake error")


class _FakeAdapter:
    def __init__(self, mt5):
        self._mt5 = mt5

    def _module(self):
        return self._mt5

    def _mt5_symbol(self, canonical):
        return canonical

    def get_latest_quote(self, symbol):
        return QuoteSnapshot(timestamp=datetime(2026, 6, 22, tzinfo=UTC),
                             symbol="EURUSD", bid=1.0999, ask=1.1001)


def _approved(notional=50_000.0):
    return (
        AccountSnapshot(equity=1_000_000, margin_level_pct=2_000),
        TradeRequest(symbol="EURUSD", side=Side.BUY, target_notional_usd=notional, reason="t"),
        RiskDecision(approved=True, reason="approved",
                     adjusted_notional_usd=notional, state=RiskState.NORMAL),
    )


class Mt5LiveExecutorTest(TestCase):
    def test_shadow_mode_does_not_place_orders(self) -> None:
        mt5 = _FakeMT5()
        with TemporaryDirectory() as d:
            j = Path(d) / "j.jsonl"
            ex = Mt5LiveExecutor(journal_path=j, market_adapter=_FakeAdapter(mt5), live=False)
            acc, req, dec = _approved()
            rec = ex.submit(account=acc, request=req, decision=dec, mode=CompetitionMode.QUALIFY)
            self.assertEqual(rec.status, "MT5_SHADOW")
            self.assertEqual(mt5.sent, [])  # no real order
            self.assertEqual(read_journal(j)[0]["platform"], "mt5_shadow")

    def test_live_places_correct_order(self) -> None:
        mt5 = _FakeMT5()
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            acc, req, dec = _approved(50_000.0)
            rec = ex.submit(account=acc, request=req, decision=dec, mode=CompetitionMode.QUALIFY)
            self.assertEqual(rec.status, "MT5_FILLED")
            self.assertEqual(len(mt5.sent), 1)
            order = mt5.sent[0]
            self.assertEqual(order["type"], _FakeMT5.ORDER_TYPE_BUY)
            # 50_000 / (100_000 * 1.10) = 0.4545 -> rounded down to 0.45 lots
            self.assertAlmostEqual(order["volume"], 0.45, places=2)
            self.assertEqual(order["type_filling"], _FakeMT5.ORDER_FILLING_IOC)

    def test_reconciles_against_existing_position(self) -> None:
        # Already long ~0.45 lots EURUSD; same 50k target => no new order.
        pos = (SimpleNamespace(symbol="EURUSD", volume=0.45, type=_FakeMT5.ORDER_TYPE_BUY),)
        mt5 = _FakeMT5(positions=pos)
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            acc, req, dec = _approved(49_500.0)  # 0.45 lots * 110_000
            rec = ex.submit(account=acc, request=req, decision=dec, mode=CompetitionMode.QUALIFY)
            self.assertEqual(rec.status, "MT5_NO_CHANGE")
            self.assertEqual(mt5.sent, [])

    def test_blocked_decision_never_trades(self) -> None:
        mt5 = _FakeMT5()
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            acc, req, _ = _approved()
            blocked = RiskDecision(approved=False, reason="frozen",
                                   adjusted_notional_usd=0.0, state=RiskState.FROZEN)
            rec = ex.submit(account=acc, request=req, decision=blocked, mode=CompetitionMode.QUALIFY)
            self.assertEqual(rec.status, "MT5_BLOCKED")
            self.assertEqual(mt5.sent, [])

    def test_max_order_lots_caps_size(self) -> None:
        mt5 = _FakeMT5()
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True, max_order_lots=0.10)
            acc, req, dec = _approved(50_000.0)  # would be 0.45 lots, capped to 0.10
            ex.submit(account=acc, request=req, decision=dec, mode=CompetitionMode.QUALIFY)
            self.assertAlmostEqual(mt5.sent[0]["volume"], 0.10, places=2)

    def test_broker_volume_step_rounds_order_size(self) -> None:
        info = SimpleNamespace(
            trade_contract_size=100_000.0,
            volume_min=0.10,
            volume_step=0.10,
            filling_mode=3,
        )
        mt5 = _FakeMT5(symbol_info=info)
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            acc, req, dec = _approved(50_000.0)
            ex.submit(account=acc, request=req, decision=dec, mode=CompetitionMode.QUALIFY)
        self.assertAlmostEqual(mt5.sent[0]["volume"], 0.40, places=2)

    def test_symbol_filling_mode_uses_fok_when_ioc_is_not_allowed(self) -> None:
        info = SimpleNamespace(
            trade_contract_size=100_000.0,
            volume_min=0.01,
            volume_step=0.01,
            filling_mode=1,
        )
        mt5 = _FakeMT5(symbol_info=info)
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            acc, req, dec = _approved(50_000.0)
            ex.submit(account=acc, request=req, decision=dec, mode=CompetitionMode.QUALIFY)
        self.assertEqual(mt5.sent[0]["type_filling"], _FakeMT5.ORDER_FILLING_FOK)

    def test_position_read_error_does_not_look_flat(self) -> None:
        mt5 = _FakeMT5(positions=None)
        ex = Mt5LiveExecutor(journal_path=Path("/tmp/unused.jsonl"),
                             market_adapter=_FakeAdapter(mt5), live=False)
        with self.assertRaisesRegex(MT5OrderError, "positions_get failed"):
            ex.current_portfolio()

    def test_flatten_all_closes_each_position_live(self) -> None:
        pos = (
            SimpleNamespace(symbol="EURUSD", volume=0.45, type=_FakeMT5.ORDER_TYPE_BUY, ticket=11),
            SimpleNamespace(symbol="XAUUSD", volume=0.10, type=_FakeMT5.ORDER_TYPE_SELL, ticket=22),
        )
        mt5 = _FakeMT5(positions=pos)
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            results = ex.flatten_all(reason="test")
        self.assertEqual(len(mt5.sent), 2)
        # long EURUSD closed with a SELL; short XAUUSD closed with a BUY
        self.assertEqual(mt5.sent[0]["type"], _FakeMT5.ORDER_TYPE_SELL)
        self.assertEqual(mt5.sent[0]["position"], 11)
        self.assertEqual(mt5.sent[1]["type"], _FakeMT5.ORDER_TYPE_BUY)
        self.assertTrue(all(r["ok"] for r in results))

    def test_flatten_all_shadow_sends_nothing(self) -> None:
        pos = (SimpleNamespace(symbol="EURUSD", volume=0.45, type=_FakeMT5.ORDER_TYPE_BUY, ticket=1),)
        mt5 = _FakeMT5(positions=pos)
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=False)
            results = ex.flatten_all()
        self.assertEqual(mt5.sent, [])
        self.assertTrue(results[0]["shadow"])

    def test_flatten_all_raises_when_positions_cannot_be_read(self) -> None:
        mt5 = _FakeMT5(positions=None)
        with TemporaryDirectory() as d:
            ex = Mt5LiveExecutor(journal_path=Path(d) / "j.jsonl",
                                 market_adapter=_FakeAdapter(mt5), live=True)
            with self.assertRaisesRegex(MT5OrderError, "positions_get failed"):
                ex.flatten_all()

    def test_current_portfolio_reads_live_positions(self) -> None:
        pos = (SimpleNamespace(symbol="EURUSD", volume=1.0, type=_FakeMT5.ORDER_TYPE_SELL),)
        mt5 = _FakeMT5(positions=pos)
        ex = Mt5LiveExecutor(journal_path=Path("/tmp/unused.jsonl"),
                             market_adapter=_FakeAdapter(mt5), live=False)
        pf = ex.current_portfolio()
        # 1 lot short * 110_000 notional => -110_000
        self.assertAlmostEqual(pf.notional_for_symbol("EURUSD"), -110_000.0, places=0)
