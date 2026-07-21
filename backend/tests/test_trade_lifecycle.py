import unittest
import sqlite3
from unittest.mock import patch, MagicMock
from backend.db.connection import init_db
from backend.db.repository import (
    add_trade, record_partial_close, finalize_trade, 
    get_active_trades, get_trade_history, get_performance_summary
)

class TestFullTradeLifecycle(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db")
        self.conn = sqlite3.connect(self.tmp_db.name)
        
        self.patcher = patch('backend.db.repository.get_connection', side_effect=lambda: sqlite3.connect(self.tmp_db.name))
        self.patcher_conn = patch('backend.db.connection.get_connection', side_effect=lambda: sqlite3.connect(self.tmp_db.name))
        self.mock_get_conn = self.patcher.start()
        self.mock_get_conn_init = self.patcher_conn.start()
        
        init_db()

    def tearDown(self):
        self.patcher.stop()
        self.patcher_conn.stop()
        self.conn.close()
        self.tmp_db.close()

    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.012, 0.005))
    def test_full_trade_lifecycle_tp1_tp2_tp3(self, mock_fees):
        """Simulasi Alur Penuh: Entry SHORT -> TP1 Hit (SL pndh BEP) -> TP2 Hit -> TP3 Hit (Full Profit)."""
        symbol = "BTCUSDT"
        entry_price = 66000.0
        initial_qty = 1.0  # 1 BTC SHORT
        
        # 1. Entry Trade disimpan ke Database
        add_trade(
            symbol=symbol, side="SELL", entry_price=entry_price,
            sl_price=66500.0, tp1_price=65500.0, tp2_price=65000.0, tp3_price=64500.0,
            initial_qty=initial_qty, remaining_qty=initial_qty
        )
        
        active = get_active_trades()
        self.assertEqual(len(active), 1)
        trade_id = active[0]['id']

        # 2. Event TP1 Tersentuh (50% Parsial Close di 65,500)
        # Gross PnL TP1 = 0.5 BTC * (66000 - 65500) = +250 USD
        record_partial_close(trade_id, event_type='TP1_HIT', exit_price=65500.0, qty_closed=0.5, realized_pnl_usd=250.0)
        
        active_tp1 = get_active_trades()
        self.assertEqual(active_tp1[0]['tp_stage'], 1)
        self.assertEqual(active_tp1[0]['remaining_qty'], 0.5)
        self.assertEqual(active_tp1[0]['accumulated_realized_pnl'], 250.0)

        # 3. Event TP2 Tersentuh (25% Parsial Close di 65,000)
        # Gross PnL TP2 = 0.25 BTC * (66000 - 65000) = +250 USD
        record_partial_close(trade_id, event_type='TP2_HIT', exit_price=65000.0, qty_closed=0.25, realized_pnl_usd=250.0)
        
        active_tp2 = get_active_trades()
        self.assertEqual(active_tp2[0]['tp_stage'], 2)
        self.assertEqual(active_tp2[0]['remaining_qty'], 0.25)
        self.assertEqual(active_tp2[0]['accumulated_realized_pnl'], 500.0)

        # 4. Event TP3 Tersentuh (25% Sisa Posisi Close di 64,500)
        # Sisa Gross PnL TP3 = 0.25 BTC * (66000 - 64500) = +375 USD
        # Total Gross PnL = 250 + 250 + 375 = +875 USD
        summary = finalize_trade(trade_id, close_price=64500.0, close_reason="FULL_TP")
        
        # Total Net PnL = 875 Gross - 0.012 Komisi + 0.005 Funding = +874.993 USD
        self.assertIsNotNone(summary)
        self.assertAlmostEqual(summary['net_pnl_usd'], 874.993, places=3)
        self.assertEqual(summary['close_reason'], "FULL_TP")

        # Verifikasi Jurnal History & Summary Performa
        history = get_trade_history(limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['symbol'], "BTCUSDT")

        perf = get_performance_summary()
        self.assertEqual(perf['total_trades'], 1)
        self.assertEqual(perf['winning_trades'], 1)

if __name__ == "__main__":
    unittest.main()
