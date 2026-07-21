import unittest
import sqlite3
from unittest.mock import patch
from backend.db.connection import init_db
from backend.db.repository import (
    add_trade, record_partial_close, finalize_trade,
    get_active_trades, get_trade_history, get_performance_summary
)

def make_db_patcher(tmp_db_name):
    p1 = patch('backend.db.repository.get_connection', side_effect=lambda: sqlite3.connect(tmp_db_name))
    p2 = patch('backend.db.connection.get_connection', side_effect=lambda: sqlite3.connect(tmp_db_name))
    return p1, p2


class TestFullTradeLifecycle(unittest.TestCase):

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
    # Skenario 1: Entry → TP1 → TP2 → TP3 → Full Profit (sudah ada)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.012, 0.005))
    def test_scenario_1_full_tp_short(self, mock_fees):
        """Simulasi alur penuh SHORT: Entry → TP1 (50%) → TP2 (25%) → TP3 (25%) → Full Profit."""
        add_trade(
            symbol="BTCUSDT", side="SELL", entry_price=66000.0,
            sl_price=66500.0, tp1_price=65500.0, tp2_price=65000.0, tp3_price=64500.0,
            initial_qty=1.0, remaining_qty=1.0
        )
        trade_id = get_active_trades()[0]['id']

        # TP1: 50% closed @ 65500 → Gross PnL = 0.5 * (66000-65500) = +250
        record_partial_close(trade_id, 'TP1_HIT', 65500.0, 0.5, 250.0)
        t = get_active_trades()[0]
        self.assertEqual(t['tp_stage'], 1)
        self.assertEqual(t['remaining_qty'], 0.5)
        self.assertEqual(t['accumulated_realized_pnl'], 250.0)

        # TP2: 25% closed @ 65000 → Gross PnL = 0.25 * (66000-65000) = +250
        record_partial_close(trade_id, 'TP2_HIT', 65000.0, 0.25, 250.0)
        t = get_active_trades()[0]
        self.assertEqual(t['tp_stage'], 2)
        self.assertEqual(t['remaining_qty'], 0.25)
        self.assertEqual(t['accumulated_realized_pnl'], 500.0)

        # TP3: 25% sisa @ 64500 → Gross PnL = 0.25 * (66000-64500) = +375
        # Total Gross = 250 + 250 + 375 = +875 | Net = 875 - 0.012 + 0.005 = 874.993
        summary = finalize_trade(trade_id, close_price=64500.0, close_reason="FULL_TP")
        self.assertIsNotNone(summary)
        self.assertAlmostEqual(summary['net_pnl_usd'], 874.993, places=3)
        self.assertEqual(summary['close_reason'], "FULL_TP")

        history = get_trade_history(limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['symbol'], "BTCUSDT")

        perf = get_performance_summary()
        self.assertEqual(perf['total_trades'], 1)
        self.assertEqual(perf['winning_trades'], 1)
        self.assertEqual(perf['losing_trades'], 0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 2 [BARU]: Entry → TP1 Hit → Balik arah kena SL BEP (Risk-Free)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.0, 0.0))
    def test_scenario_2_tp1_then_sl_bep(self, mock_fees):
        """SHORT: TP1 Hit (profit +250) → harga balik arah → kena SL di Break-Even Entry.
        Net PnL ≈ +250 (only TP1 profit realized, remaining closed at entry = 0 P&L)."""
        add_trade(
            symbol="ETHUSDT", side="SELL", entry_price=2500.0,
            sl_price=2550.0, tp1_price=2450.0, tp2_price=2400.0, tp3_price=2350.0,
            initial_qty=1.0, remaining_qty=1.0
        )
        trade_id = get_active_trades()[0]['id']

        # TP1 tersentuh: 50% closed @ 2450 → Gross PnL = 0.5 * (2500-2450) = +25
        record_partial_close(trade_id, 'TP1_HIT', 2450.0, 0.5, 25.0)
        t = get_active_trades()[0]
        self.assertEqual(t['tp_stage'], 1)
        self.assertEqual(t['accumulated_realized_pnl'], 25.0)

        # SL dipindahkan ke BEP (2500), lalu harga balik menyentuh SL @ 2500
        # Gross PnL Sisa = 0.5 * (2500 - 2500) = 0.0
        summary = finalize_trade(trade_id, close_price=2500.0, close_reason="SL_BEP")
        self.assertIsNotNone(summary)
        self.assertEqual(summary['close_reason'], "SL_BEP")
        # Net PnL = 25 (dari TP1) + 0 (sisa ditutup di BEP) = +25
        self.assertAlmostEqual(summary['net_pnl_usd'], 25.0, places=2)
        # Trade ini WINNING karena Net PnL > 0
        perf = get_performance_summary()
        self.assertEqual(perf['winning_trades'], 1)
        self.assertEqual(perf['losing_trades'], 0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 3 [BARU]: Entry → Langsung kena Stop Loss awal (full loss)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.10, 0.0))
    def test_scenario_3_direct_sl_hit(self, mock_fees):
        """SHORT: Harga langsung naik menyentuh SL tanpa menyentuh TP1 sama sekali.
        Net PnL harus negatif dan losing_trades naik."""
        add_trade(
            symbol="BTCUSDT", side="SELL", entry_price=66000.0,
            sl_price=66500.0, tp1_price=65500.0, tp2_price=65000.0, tp3_price=64500.0,
            initial_qty=0.1, remaining_qty=0.1
        )
        trade_id = get_active_trades()[0]['id']
        self.assertEqual(get_active_trades()[0]['tp_stage'], 0)  # TP1 belum hit

        # Langsung tutup di SL = 66500
        # Gross PnL = 0.1 * (66000 - 66500) = -50 USDT
        summary = finalize_trade(trade_id, close_price=66500.0, close_reason="SL_HIT")
        self.assertIsNotNone(summary)
        self.assertEqual(summary['close_reason'], "SL_HIT")
        self.assertLess(summary['net_pnl_usd'], 0.0)

        self.assertEqual(len(get_active_trades()), 0)

        perf = get_performance_summary()
        self.assertEqual(perf['total_trades'], 1)
        self.assertEqual(perf['winning_trades'], 0)
        self.assertEqual(perf['losing_trades'], 1)
        self.assertLess(perf['total_net_pnl'], 0.0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 4 [BARU]: LONG trade full lifecycle (BUY)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.0, 0.0))
    def test_scenario_4_full_tp_long(self, mock_fees):
        """Simulasi alur penuh LONG BUY: Entry → TP1 (50%) → TP2 (25%) → TP3 (25%) → Full Profit."""
        add_trade(
            symbol="SOLUSDT", side="BUY", entry_price=145.0,
            sl_price=140.0, tp1_price=150.0, tp2_price=155.0, tp3_price=160.0,
            initial_qty=10.0, remaining_qty=10.0
        )
        trade_id = get_active_trades()[0]['id']

        # TP1: 50% closed @ 150 → Gross PnL = 5 * (150-145) = +25
        record_partial_close(trade_id, 'TP1_HIT', 150.0, 5.0, 25.0)
        t = get_active_trades()[0]
        self.assertEqual(t['tp_stage'], 1)
        self.assertEqual(t['remaining_qty'], 5.0)

        # TP2: 25% closed @ 155 → Gross PnL = 2.5 * (155-145) = +25
        record_partial_close(trade_id, 'TP2_HIT', 155.0, 2.5, 25.0)
        t = get_active_trades()[0]
        self.assertEqual(t['tp_stage'], 2)

        # TP3: 25% sisa @ 160 → Gross PnL = 2.5 * (160-145) = +37.5
        # Total Gross = 25 + 25 + 37.5 = +87.5
        summary = finalize_trade(trade_id, close_price=160.0, close_reason="FULL_TP")
        self.assertIsNotNone(summary)
        self.assertAlmostEqual(summary['net_pnl_usd'], 87.5, places=2)
        self.assertEqual(summary['close_reason'], "FULL_TP")

        perf = get_performance_summary()
        self.assertEqual(perf['total_trades'], 1)
        self.assertEqual(perf['winning_trades'], 1)

    # ────────────────────────────────────────────────────────────────
    # Skenario 5 [BARU]: Campuran win + loss → win rate 50%
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_official_trade_fees', return_value=(0.0, 0.0))
    def test_scenario_5_mixed_win_and_loss(self, mock_fees):
        """1 trade WIN + 1 trade LOSS → total_trades=2, win_rate=50%."""
        # Trade 1: WIN (SHORT TP)
        t1 = add_trade("BTCUSDT", "SELL", 66000.0, 66500.0, 65500.0, 65000.0, 64500.0, 0.1, 0.1)
        finalize_trade(t1, close_price=64500.0, close_reason="FULL_TP")

        # Trade 2: LOSS (SHORT SL)
        t2 = add_trade("ETHUSDT", "SELL", 2500.0, 2550.0, 2450.0, 2400.0, 2350.0, 1.0, 1.0)
        finalize_trade(t2, close_price=2550.0, close_reason="SL_HIT")

        perf = get_performance_summary()
        self.assertEqual(perf['total_trades'], 2)
        self.assertEqual(perf['winning_trades'], 1)
        self.assertEqual(perf['losing_trades'], 1)


if __name__ == "__main__":
    unittest.main()
