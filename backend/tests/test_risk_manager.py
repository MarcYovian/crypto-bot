import unittest
from unittest.mock import patch, MagicMock
from backend.core.risk_manager import round_step, calculate_position_size

class TestRiskManager(unittest.TestCase):

    # ────────────────────────────────────────────────────────────────
    # round_step() Tests
    # ────────────────────────────────────────────────────────────────
    def test_round_step_three_decimals(self):
        """Step size 0.001 → pembulatan 3 desimal."""
        self.assertEqual(round_step(12.34567, 0.001), 12.346)

    def test_round_step_integer(self):
        """Step size 1.0 → pembulatan ke bilangan bulat."""
        self.assertEqual(round_step(104.7, 1.0), 105.0)

    def test_round_step_one_decimal(self):
        """Step size 0.1 → pembulatan 1 desimal."""
        self.assertEqual(round_step(66770.43, 0.1), 66770.4)

    def test_round_step_zero_stepsize(self):
        """Step size 0 atau None → kembalikan nilai asli tanpa error."""
        self.assertEqual(round_step(12.5, 0), 12.5)
        self.assertEqual(round_step(12.5, None), 12.5)

    # ────────────────────────────────────────────────────────────────
    # calculate_position_size() - Mode DAILY_ANCHOR (sudah ada)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    @patch('backend.core.risk_manager.set_config')
    def test_calculate_position_size_daily_anchor(self, mock_set_cfg, mock_get_cfg, mock_binance_client):
        """Mode DAILY_ANCHOR: Risk Amount = Anchor * 2%, qty dihitung berdasarkan SL distance."""
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '85.0'}]
        }
        mock_binance_client.futures_position_information.return_value = [
            {'positionAmt': '1000.0', 'entryPrice': '0.225'}  # Margin = 15 USDT
        ]
        def get_cfg_side_effect(key, default=None):
            return {'risk_mode': 'DAILY_ANCHOR', 'risk_pct': '0.02', 'daily_anchor_balance': '100.0'}.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        # Risk = $100 * 2% = $2.0 | SL dist = 5% | Size = $2/0.05 = $40 | Qty = 40/100 = 0.4
        qty = calculate_position_size("BTCUSDT", entry_price=100.0, sl_price=95.0, step_size=0.001)
        self.assertEqual(qty, 0.4)

    # ────────────────────────────────────────────────────────────────
    # calculate_position_size() - Mode FIXED_USD (sudah ada)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    def test_calculate_position_size_fixed_usd(self, mock_get_cfg, mock_binance_client):
        """Mode FIXED_USD: Risk Amount = nilai tetap $2.5 per trade."""
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '50.0'}]
        }
        mock_binance_client.futures_position_information.return_value = []
        def get_cfg_side_effect(key, default=None):
            return {'risk_mode': 'FIXED_USD', 'fixed_risk_usd': '2.5', 'daily_anchor_balance': '50.0'}.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        # Risk = $2.5 Fixed | SL dist = 10% | Size = $2.5/0.10 = $25 | Qty = 25/10 = 2.5
        qty = calculate_position_size("SOLUSDT", entry_price=10.0, sl_price=9.0, step_size=0.1)
        self.assertEqual(qty, 2.5)

    # ────────────────────────────────────────────────────────────────
    # [BARU] Kasus sl_price == entry_price (SL Distance = 0%)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    def test_calculate_position_size_zero_sl_distance(self, mock_get_cfg, mock_binance_client):
        """Jika entry == SL (SL distance 0%), harus return 0.0 tanpa exception."""
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '100.0'}]
        }
        mock_binance_client.futures_position_information.return_value = []
        def get_cfg_side_effect(key, default=None):
            return {'risk_mode': 'DAILY_ANCHOR', 'risk_pct': '0.02', 'daily_anchor_balance': '100.0'}.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        qty = calculate_position_size("BTCUSDT", entry_price=66000.0, sl_price=66000.0, step_size=0.001)
        self.assertEqual(qty, 0.0)

    # ────────────────────────────────────────────────────────────────
    # [BARU] Kasus daily_anchor_balance = 0 → inisialisasi otomatis dari Total Equity
    # ────────────────────────────────────────────────────────────────
    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    @patch('backend.core.risk_manager.set_config')
    def test_calculate_position_size_anchor_initialization(self, mock_set_cfg, mock_get_cfg, mock_binance_client):
        """Jika daily_anchor_balance = 0, harus inisialisasi dari Total Equity dan panggil set_config."""
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '200.0'}]
        }
        mock_binance_client.futures_position_information.return_value = []  # Tidak ada posisi terbuka
        def get_cfg_side_effect(key, default=None):
            return {'risk_mode': 'DAILY_ANCHOR', 'risk_pct': '0.02', 'daily_anchor_balance': '0.0'}.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        # Total Equity = 200 USDT (tidak ada posisi, semua available)
        # Anchor diinisialisasi ke 200, Risk = 200 * 2% = 4.0
        # SL dist = 5% | Qty = (4.0/0.05)/100 = 0.8
        qty = calculate_position_size("BTCUSDT", entry_price=100.0, sl_price=95.0, step_size=0.001)

        # Verifikasi set_config dipanggil untuk menyimpan anchor_balance baru
        mock_set_cfg.assert_called_once()
        call_args = mock_set_cfg.call_args[0]
        self.assertEqual(call_args[0], "daily_anchor_balance")
        self.assertEqual(float(call_args[1]), 200.0)
        self.assertEqual(qty, 0.8)

    # ────────────────────────────────────────────────────────────────
    # [BARU] Kasus risk_pct kustom dari sinyal (override parameter)
    # ────────────────────────────────────────────────────────────────
    @patch('backend.core.risk_manager.client')
    @patch('backend.core.risk_manager.get_config')
    @patch('backend.core.risk_manager.set_config')
    def test_calculate_position_size_custom_risk_pct_from_signal(self, mock_set_cfg, mock_get_cfg, mock_binance_client):
        """Risk% dari sinyal (parameter risk_pct) harus override nilai DB."""
        mock_binance_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '100.0'}]
        }
        mock_binance_client.futures_position_information.return_value = []
        def get_cfg_side_effect(key, default=None):
            return {'risk_mode': 'DAILY_ANCHOR', 'risk_pct': '0.02', 'daily_anchor_balance': '100.0'}.get(key, default)
        mock_get_cfg.side_effect = get_cfg_side_effect

        # Sinyal mengirim risk_pct = 1.5% (0.015) bukan 2% dari DB
        # Risk = $100 * 1.5% = $1.5 | SL dist = 5% | Qty = ($1.5/0.05)/100 = 0.3
        qty = calculate_position_size("BTCUSDT", entry_price=100.0, sl_price=95.0, step_size=0.001, risk_pct=0.015)
        self.assertEqual(qty, 0.3)


if __name__ == "__main__":
    unittest.main()
