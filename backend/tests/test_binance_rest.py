import unittest
from unittest.mock import patch, MagicMock
from backend.services.binance_rest import execute_trade, get_official_trade_fees

class TestBinanceRESTService(unittest.TestCase):

    @patch('backend.services.binance_rest.get_symbol_info')
    @patch('backend.services.binance_rest.calculate_position_size')
    @patch('backend.services.binance_rest.client')
    def test_execute_trade_margin_exceeds_available(self, mock_client, mock_calc_qty, mock_sym_info):
        # TickSize = 0.1, StepSize = 0.001, MinQty = 0.001, MaxQty = 100
        mock_sym_info.return_value = (0.1, 0.001, 0.001, 100.0)
        mock_client.futures_symbol_ticker.return_value = {'price': '66770.0'}
        
        # Kalkulasi Qty dari risk manager = 0.1 BTC (Margin = (0.1 * 66770) / 15 = 445.13 USDT)
        mock_calc_qty.return_value = 0.1
        
        # Available Balance cuma ada 100.0 USDT (Kurang!)
        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '100.0'}]
        }
        
        signal_data = {
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'entry': 66770.0,
            'sl': 66900.0,
            'tp1': 66600.0,
            'tp2': 66500.0,
            'tp3': 66400.0
        }
        
        res = execute_trade(signal_data)
        # Harus mengembalikan pesan MARGIN_EXCEEDS_AVAILABLE
        self.assertTrue(isinstance(res, str))
        self.assertTrue(res.startswith("MARGIN_EXCEEDS_AVAILABLE:"))

    @patch('backend.services.binance_rest.client')
    def test_get_official_trade_fees(self, mock_client):
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

if __name__ == "__main__":
    unittest.main()
