import unittest
from unittest.mock import patch, MagicMock
from backend.core.risk_manager import round_step, calculate_position_size

class TestRiskManager(unittest.TestCase):

    def test_round_step(self):
        # Test step size = 0.001 (3 desimal)
        self.assertEqual(round_step(12.34567, 0.001), 12.346)
        # Test step size = 1.0 (bilangan bulat)
        self.assertEqual(round_step(104.7, 1.0), 105.0)
        # Test step size = 0.1
        self.assertEqual(round_step(66770.43, 0.1), 66770.4)

    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    @patch('backend.core.risk_manager.set_config')
    def test_calculate_position_size_daily_anchor(self, mock_set_cfg, mock_get_cfg, mock_binance_client):
        # Mock Binance futures account info
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '85.0'}]
        }
        # Mock posisi aktif menggantung (1 posisi dengan margin 15 USDT)
        mock_binance_client.futures_position_information.return_value = [
            {'positionAmt': '1000.0', 'entryPrice': '0.225'}  # Margin = (1000*0.225)/15 = 15 USDT
        ]
        
        # Mock SQLite config values
        def get_cfg_side_effect(key, default=None):
            cfg_map = {
                'risk_mode': 'DAILY_ANCHOR',
                'risk_pct': '0.02',
                'daily_anchor_balance': '100.0'  # Fixed 100 USDT harian
            }
            return cfg_map.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        # Entry = 100, SL = 95 -> SL Distance = 5% (0.05)
        # Risk Amount = 100 * 2% = 2.0 USDT
        # Position Size USD = 2.0 / 0.05 = 40 USDT
        # Qty = 40 / 100 = 0.4 koin
        qty = calculate_position_size("BTCUSDT", entry_price=100.0, sl_price=95.0, step_size=0.001)
        self.assertEqual(qty, 0.4)

    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    def test_calculate_position_size_fixed_usd(self, mock_get_cfg, mock_binance_client):
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '50.0'}]
        }
        mock_binance_client.futures_position_information.return_value = []

        def get_cfg_side_effect(key, default=None):
            cfg_map = {
                'risk_mode': 'FIXED_USD',
                'fixed_risk_usd': '2.5',
                'daily_anchor_balance': '50.0'
            }
            return cfg_map.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        # Entry = 10.0, SL = 9.0 -> SL Distance = 10% (0.10)
        # Risk Amount Fixed = 2.5 USDT
        # Position Size USD = 2.5 / 0.10 = 25 USDT
        # Qty = 25 / 10 = 2.5 koin
        qty = calculate_position_size("SOLUSDT", entry_price=10.0, sl_price=9.0, step_size=0.1)
        self.assertEqual(qty, 2.5)

if __name__ == "__main__":
    unittest.main()
