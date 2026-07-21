import unittest
from unittest.mock import patch, MagicMock
from backend.services.binance_rest import execute_trade, get_official_trade_fees

class TestBinanceRESTService(unittest.TestCase):

    # ────────────────────────────────────────────────────────────────
    # Skenario 1: MARGIN_EXCEEDS_AVAILABLE (sudah ada)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_margin_exceeds_available(self, mock_client, mock_calc_qty, mock_sym_info):
        """Jika Required Margin > Available Balance → return MARGIN_EXCEEDS_AVAILABLE."""
        mock_sym_info.return_value = (0.1, 0.001, 0.001, 100.0)
        mock_client.futures_symbol_ticker.return_value = {'price': '66770.0'}
        mock_calc_qty.return_value = 0.1  # Margin = (0.1 * 66770) / 15 = 445.13 USDT
        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '100.0'}]
        }
        signal_data = {
            'symbol': 'BTCUSDT', 'side': 'SELL',
            'entry': 66770.0, 'sl': 66900.0,
            'tp1': 66600.0, 'tp2': 66500.0, 'tp3': 66400.0
        }
        res = execute_trade(signal_data)
        self.assertIsInstance(res, str)
        self.assertTrue(res.startswith("MARGIN_EXCEEDS_AVAILABLE:"))

    # ────────────────────────────────────────────────────────────────
    # Skenario 2: get_official_trade_fees (sudah ada)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.client')
    def test_get_official_trade_fees(self, mock_client):
        """Verifikasi penjumlahan komisi & funding fee dari Binance API."""
        mock_client.futures_account_trades.return_value = [
            {'commission': '0.002959'},
            {'commission': '0.003250'}
        ]
        mock_client.futures_income_history.return_value = [
            {'income': '0.005900'}
        ]
        comm, funding = get_official_trade_fees("PENGUUSDT", start_time_ms=1710000000000)
        self.assertAlmostEqual(comm, 0.006209, places=6)
        self.assertEqual(funding, 0.0059)

    # ────────────────────────────────────────────────────────────────
    # Skenario 3 [BARU]: QTY_UNDER_MIN — kuantitas di bawah minimum
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_qty_under_min(self, mock_client, mock_calc_qty, mock_sym_info):
        """Jika qty hasil kalkulasi < minQty Binance → return QTY_UNDER_MIN."""
        mock_sym_info.return_value = (0.1, 0.001, 0.01, 100.0)  # minQty = 0.01
        mock_client.futures_symbol_ticker.return_value = {'price': '66770.0'}
        mock_calc_qty.return_value = 0.001  # Kurang dari minQty = 0.01
        # Available balance cukup sehingga tidak trigger MARGIN_EXCEEDS_AVAILABLE
        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '10000.0'}]
        }
        signal_data = {
            'symbol': 'BTCUSDT', 'side': 'SELL',
            'entry': 66770.0, 'sl': 66900.0,
            'tp1': 66600.0, 'tp2': 66500.0, 'tp3': 66400.0
        }
        res = execute_trade(signal_data)
        self.assertIsInstance(res, str)
        self.assertTrue(res.startswith("QTY_UNDER_MIN:"))

    # ────────────────────────────────────────────────────────────────
    # Skenario 4 [BARU]: QTY_OVER_MAX — kuantitas melebihi maksimum
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_qty_over_max(self, mock_client, mock_calc_qty, mock_sym_info):
        """Jika qty hasil kalkulasi > maxQty Binance → return QTY_OVER_MAX."""
        mock_sym_info.return_value = (0.1, 0.001, 0.001, 5.0)  # maxQty = 5.0
        mock_client.futures_symbol_ticker.return_value = {'price': '66770.0'}
        mock_calc_qty.return_value = 10.0  # Lebih dari maxQty = 5.0
        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '10000.0'}]
        }
        signal_data = {
            'symbol': 'BTCUSDT', 'side': 'SELL',
            'entry': 66770.0, 'sl': 66900.0,
            'tp1': 66600.0, 'tp2': 66500.0, 'tp3': 66400.0
        }
        res = execute_trade(signal_data)
        self.assertIsInstance(res, str)
        self.assertTrue(res.startswith("QTY_OVER_MAX:"))

    # ────────────────────────────────────────────────────────────────
    # Skenario 5 [BARU]: Market Order sukses (happy path SELL SHORT)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.add_trade')
    @patch('backend.services.binance_rest.place_partial_tps')
    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_market_order_success(self, mock_client, mock_calc_qty, mock_sym_info, mock_place_tps, mock_add_trade):
        """Happy path: Market order SHORT berhasil dieksekusi, return pesan sukses."""
        mock_sym_info.return_value = (0.1, 0.001, 0.001, 100.0)
        mock_client.futures_symbol_ticker.return_value = {'price': '66760.0'}  # Di dalam toleransi 0.2%
        mock_calc_qty.return_value = 0.01
        # Available balance jauh lebih besar dari required margin (aman)
        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '5000.0'}]
        }
        # Leverage & margin type change OK
        mock_client.futures_change_leverage.return_value = {}
        mock_client.futures_change_margin_type.return_value = {}
        # Market order berhasil
        mock_client.futures_create_order.return_value = {'orderId': 12345}
        # Verifikasi posisi aktif terbuka
        mock_client.futures_position_information.return_value = [
            {'positionAmt': '-0.01', 'entryPrice': '66760.0'}
        ]
        mock_place_tps.return_value = ('111', '222', '333')
        mock_add_trade.return_value = 1

        signal_data = {
            'symbol': 'BTCUSDT', 'side': 'SELL',
            'entry': 66770.0, 'sl': 66900.0,
            'tp1': 66600.0, 'tp2': 66500.0, 'tp3': 66400.0
        }
        res = execute_trade(signal_data)
        self.assertIsInstance(res, str)
        # Harus mengandung kata "Berhasil" untuk sukses
        self.assertIn("Berhasil", res)

    # ────────────────────────────────────────────────────────────────
    # Skenario 6 [BARU]: Limit Order sukses (harga di luar toleransi 0.2%)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.add_trade')
    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_limit_order_success(self, mock_client, mock_calc_qty, mock_sym_info, mock_add_trade):
        """Ketika harga pasar jauh di bawah entry SHORT (di luar toleransi 0.2%), harus pasang LIMIT order."""
        mock_sym_info.return_value = (0.1, 0.001, 0.001, 100.0)
        # Untuk SHORT SELL, harga pasar 65000 < entry 66770 * (1 - 0.2%) = 66636 → di luar toleransi → LIMIT
        mock_client.futures_symbol_ticker.return_value = {'price': '65000.0'}
        mock_calc_qty.return_value = 0.01
        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '5000.0'}]
        }
        mock_client.futures_change_leverage.return_value = {}
        mock_client.futures_change_margin_type.return_value = {}
        mock_client.futures_create_order.return_value = {'orderId': 99999}
        mock_add_trade.return_value = 1

        signal_data = {
            'symbol': 'BTCUSDT', 'side': 'SELL',
            'entry': 66770.0, 'sl': 66900.0,
            'tp1': 66600.0, 'tp2': 66500.0, 'tp3': 66400.0
        }
        res = execute_trade(signal_data)
        self.assertIsInstance(res, str)
        # Harus mengandung kata 'Memasang LIMIT' untuk limit order
        self.assertIn("Memasang LIMIT", res)

    # ────────────────────────────────────────────────────────────────
    # Skenario 7 [BARU]: override_qty dari konfirmasi Telegram (bypass margin check)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.add_trade')
    @patch('backend.services.binance_rest.place_partial_tps')
    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_with_override_qty_bypasses_margin_check(self, mock_client, mock_calc_qty, mock_sym_info, mock_place_tps, mock_add_trade):
        """override_qty di signal_data harus melewati pengecekan margin & batas min/max."""
        mock_sym_info.return_value = (0.1, 0.001, 0.001, 100.0)
        mock_client.futures_symbol_ticker.return_value = {'price': '66760.0'}
        mock_calc_qty.return_value = 0.1  # Tidak digunakan karena override
        mock_client.futures_change_leverage.return_value = {}
        mock_client.futures_change_margin_type.return_value = {}
        mock_client.futures_create_order.return_value = {'orderId': 55555}
        mock_client.futures_position_information.return_value = [
            {'positionAmt': '-0.005', 'entryPrice': '66760.0'}
        ]
        mock_place_tps.return_value = ('a', 'b', 'c')
        mock_add_trade.return_value = 1

        signal_data = {
            'symbol': 'BTCUSDT', 'side': 'SELL',
            'entry': 66770.0, 'sl': 66900.0,
            'tp1': 66600.0, 'tp2': 66500.0, 'tp3': 66400.0,
            'override_qty': 0.005  # Langsung pakai qty ini
        }
        res = execute_trade(signal_data)
        self.assertIsInstance(res, str)
        # Tidak boleh trigger margin check karena override_qty diset
        self.assertFalse(res.startswith("MARGIN_EXCEEDS_AVAILABLE:"))
        self.assertIn("Berhasil", res)

    # ────────────────────────────────────────────────────────────────
    # Skenario 8 [BARU]: get_official_trade_fees dengan tidak ada trade
    # ────────────────────────────────────────────────────────────────
    @patch('backend.services.binance_rest.client')
    def test_get_official_trade_fees_no_trades(self, mock_client):
        """Jika tidak ada trade & funding di Binance → comm=0.0, funding=0.0."""
        mock_client.futures_account_trades.return_value = []
        mock_client.futures_income_history.return_value = []
        comm, funding = get_official_trade_fees("BTCUSDT", start_time_ms=1710000000000)
        self.assertEqual(comm, 0.0)
        self.assertEqual(funding, 0.0)


if __name__ == "__main__":
    unittest.main()
