import unittest
import sqlite3
from unittest.mock import patch
from backend.db.connection import init_db
from backend.db.repository import (
    add_trade, record_partial_close, finalize_trade,
    get_active_trades, get_trade_history, get_performance_summary,
    get_config, set_config, get_all_configs, get_trade_by_id
)

def make_db_patcher(tmp_db_name):
    """Helper: Buat patcher untuk koneksi DB ke file temp."""
    p1 = patch('backend.db.repository.get_connection', side_effect=lambda: sqlite3.connect(tmp_db_name))
    p2 = patch('backend.db.connection.get_connection', side_effect=lambda: sqlite3.connect(tmp_db_name))
    return p1, p2


class TestRepositoryCRUD(unittest.TestCase):
    """Pengujian CRUD dasar active_trades dan finalisasi ke trade_history."""

    def setUp(self):
        import tempfile
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db")
        self.p1, self.p2 = make_db_patcher(self.tmp_db.name)
        self.p1.start(); self.p2.start()
        init_db()

    def tearDown(self):
        self.p1.stop(); self.p2.stop()
        self.tmp_db.close()

    # ────────────────────────────────────────────────────────────────
    # Skenario 1: Add trade & finalize (sudah ada, diperkuat)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.05, 0.01))
    def test_add_and_finalize_trade(self, mock_fees):
        """add_trade → record_partial_close → finalize_trade → active_trades kosong."""
        add_trade(
            symbol="BTCUSDT", side="SELL", entry_price=66000.0,
            sl_price=66500.0, tp1_price=65500.0, tp2_price=65000.0, tp3_price=64500.0,
            initial_qty=0.1, remaining_qty=0.1
        )
        trades = get_active_trades()
        self.assertEqual(len(trades), 1)
        trade_id = trades[0]['id']

        record_partial_close(trade_id, event_type='TP1_HIT', exit_price=65500.0, qty_closed=0.05, realized_pnl_usd=25.0)
        trades_after_tp1 = get_active_trades()
        self.assertEqual(trades_after_tp1[0]['tp_stage'], 1)
        self.assertAlmostEqual(trades_after_tp1[0]['remaining_qty'], 0.05)

        summary = finalize_trade(trade_id, close_price=64500.0, close_reason="FULL_TP")
        self.assertIsNotNone(summary)
        self.assertEqual(summary['close_reason'], "FULL_TP")
        self.assertEqual(len(get_active_trades()), 0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 2 [BARU]: get_trade_by_id — verifikasi data record
    # ────────────────────────────────────────────────────────────────
    def test_get_trade_by_id(self):
        """get_trade_by_id harus mengembalikan trade yang benar."""
        trade_id = add_trade(
            symbol="SOLUSDT", side="BUY", entry_price=145.0,
            sl_price=140.0, tp1_price=150.0, tp2_price=155.0, tp3_price=160.0,
            initial_qty=10.0, remaining_qty=10.0
        )
        trade = get_trade_by_id(trade_id)
        self.assertIsNotNone(trade)
        self.assertEqual(trade['symbol'], "SOLUSDT")
        self.assertEqual(trade['side'], "BUY")
        self.assertEqual(trade['initial_qty'], 10.0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 3 [BARU]: Multiple concurrent trades untuk 2 symbol
    # ────────────────────────────────────────────────────────────────
    def test_multiple_concurrent_trades(self):
        """Dua trade berbeda (BTCUSDT + SOLUSDT) harus bisa aktif bersamaan."""
        add_trade("BTCUSDT", "SELL", 66000.0, 66500.0, 65500.0, 65000.0, 64500.0, 0.1, 0.1)
        add_trade("SOLUSDT", "BUY", 145.0, 140.0, 150.0, 155.0, 160.0, 10.0, 10.0)

        trades = get_active_trades()
        self.assertEqual(len(trades), 2)
        symbols = {t['symbol'] for t in trades}
        self.assertIn("BTCUSDT", symbols)
        self.assertIn("SOLUSDT", symbols)

    # ────────────────────────────────────────────────────────────────
    # Skenario 4 [BARU]: SL_HIT → Net PnL negatif → losing_trades naik
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.10, 0.0))
    def test_finalize_sl_hit_negative_pnl(self, mock_fees):
        """Trade tutup karena SL_HIT harus menghasilkan Net PnL negatif."""
        trade_id = add_trade(
            symbol="BTCUSDT", side="SELL", entry_price=66000.0,
            sl_price=66500.0, tp1_price=65500.0, tp2_price=65000.0, tp3_price=64500.0,
            initial_qty=0.1, remaining_qty=0.1
        )
        # Harga naik menyentuh SL (SHORT kena SL = loss)
        summary = finalize_trade(trade_id, close_price=66500.0, close_reason="SL_HIT")
        self.assertIsNotNone(summary)
        self.assertEqual(summary['close_reason'], "SL_HIT")
        # SHORT entry 66000, close di 66500 → Gross PnL = 0.1 * (66000 - 66500) = -50
        self.assertLess(summary['net_pnl_usd'], 0)

        perf = get_performance_summary()
        self.assertEqual(perf['total_trades'], 1)
        self.assertEqual(perf['winning_trades'], 0)
        self.assertEqual(perf['losing_trades'], 1)

    # ────────────────────────────────────────────────────────────────
    # Skenario 5 [BARU]: get_trade_history → verifikasi data tersimpan
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.0, 0.0))
    def test_get_trade_history_after_finalize(self, mock_fees):
        """Setelah finalize_trade, record harus muncul di trade_history."""
        trade_id = add_trade(
            symbol="ETHUSDT", side="BUY", entry_price=2500.0,
            sl_price=2400.0, tp1_price=2600.0, tp2_price=2700.0, tp3_price=2800.0,
            initial_qty=1.0, remaining_qty=1.0
        )
        finalize_trade(trade_id, close_price=2800.0, close_reason="FULL_TP")

        history = get_trade_history(limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['symbol'], "ETHUSDT")
        self.assertEqual(history[0]['close_reason'], "FULL_TP")

    # ────────────────────────────────────────────────────────────────
    # Skenario 6: bot_config CRUD (sudah ada, diperkuat)
    # ────────────────────────────────────────────────────────────────
    def test_bot_config_crud(self):
        """get_config, set_config, get_all_configs bekerja benar."""
        self.assertEqual(get_config('risk_mode'), 'DAILY_ANCHOR')

        set_config('daily_anchor_balance', '150.5')
        self.assertEqual(get_config('daily_anchor_balance'), '150.5')

        configs = get_all_configs()
        self.assertIn('risk_mode', configs)
        self.assertEqual(configs['daily_anchor_balance'], '150.5')

    # ────────────────────────────────────────────────────────────────
    # Skenario 7 [BARU]: get_config dengan key tidak ada → return default
    # ────────────────────────────────────────────────────────────────
    def test_get_config_missing_key_returns_default(self):
        """get_config dengan key tidak ada harus return nilai default."""
        result = get_config('kunci_tidak_ada', default='fallback_value')
        self.assertEqual(result, 'fallback_value')

    # ────────────────────────────────────────────────────────────────
    # Skenario 8 [BARU]: set_config idempotent (update duplikat)
    # ────────────────────────────────────────────────────────────────
    def test_set_config_is_idempotent(self):
        """set_config yang dipanggil 2x untuk key yang sama harus update, bukan duplikat."""
        set_config('risk_pct', '0.03')
        set_config('risk_pct', '0.01')  # Update lagi
        self.assertEqual(get_config('risk_pct'), '0.01')


if __name__ == "__main__":
    unittest.main()
