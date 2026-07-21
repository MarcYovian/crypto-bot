import unittest
import sqlite3
from unittest.mock import patch
from backend.db.connection import init_db
from backend.db.repository import (
    add_trade, record_partial_close, finalize_trade, 
    get_active_trades, get_config, set_config, get_all_configs
)

class TestRepository(unittest.TestCase):

    def setUp(self):
        # Buat file DB temporary disk agar koneksi SQLite konsisten
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

    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.05, 0.01))
    def test_add_and_finalize_trade(self, mock_fees):
        # 1. Tambahkan trade baru
        add_trade(
            symbol="BTCUSDT", side="SELL", entry_price=66000.0,
            sl_price=66500.0, tp1_price=65500.0, tp2_price=65000.0, tp3_price=64500.0,
            initial_qty=0.1, remaining_qty=0.1
        )
        
        trades = get_active_trades()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]['symbol'], "BTCUSDT")
        trade_id = trades[0]['id']

        # 2. Record Partial Close TP1 (50%)
        record_partial_close(trade_id, event_type='TP1_HIT', exit_price=65500.0, qty_closed=0.05, realized_pnl_usd=25.0)
        
        trades_after_tp1 = get_active_trades()
        self.assertEqual(trades_after_tp1[0]['tp_stage'], 1)
        self.assertAlmostEqual(trades_after_tp1[0]['remaining_qty'], 0.05)

        # 3. Finalize Trade pada TP3
        summary = finalize_trade(trade_id, close_price=64500.0, close_reason="FULL_TP")
        self.assertIsNotNone(summary)
        self.assertEqual(summary['close_reason'], "FULL_TP")
        
        # Pastikan tidak ada trade aktif tersisa
        active_after_close = get_active_trades()
        self.assertEqual(len(active_after_close), 0)

    def test_bot_config_crud(self):
        # Test default seeds
        self.assertEqual(get_config('risk_mode'), 'DAILY_ANCHOR')
        
        # Test update config
        set_config('daily_anchor_balance', '150.5')
        self.assertEqual(get_config('daily_anchor_balance'), '150.5')
        
        configs = get_all_configs()
        self.assertIn('risk_mode', configs)
        self.assertEqual(configs['daily_anchor_balance'], '150.5')

if __name__ == "__main__":
    unittest.main()
