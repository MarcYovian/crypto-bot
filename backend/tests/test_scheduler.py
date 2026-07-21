import unittest
from unittest.mock import patch, MagicMock, call

class TestCronJobs(unittest.TestCase):
    """Pengujian fungsi-fungsi cron/scheduler tanpa menjalankan scheduler sungguhan."""

    # ────────────────────────────────────────────────────────────────
    # Skenario 1 [BARU]: cron_reset_daily_anchor_balance → set_config dipanggil
    # ────────────────────────────────────────────────────────────────
    @patch('backend.db.repository.set_config')
    @patch('backend.jobs.scheduler.client')
    def test_cron_reset_daily_anchor_balance(self, mock_client, mock_set_config):
        """cron_reset_daily_anchor_balance harus memanggil set_config dengan Total Equity yang benar."""
        from backend.jobs.scheduler import cron_reset_daily_anchor_balance

        mock_client.futures_account.return_value = {
            'assets': [{'asset': 'USDT', 'availableBalance': '500.0'}]
        }
        # 1 posisi aktif SHORT dengan PosAmt -0.1 BTC @ entry 66000 → Margin = 0.1*66000/15 = 440 USDT
        mock_client.futures_position_information.return_value = [
            {'positionAmt': '-0.1', 'entryPrice': '66000.0'}
        ]

        cron_reset_daily_anchor_balance()

        # Total Equity = 500 + 440 = 940 USDT
        mock_set_config.assert_called_once_with("daily_anchor_balance", 940.0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 2 [BARU]: cron_check_margin_level → alert dikirim saat < 15%
    # ────────────────────────────────────────────────────────────────
    @patch('backend.jobs.scheduler.bot')
    @patch('backend.jobs.scheduler.ALLOWED_USER_ID', 123456)
    @patch('backend.jobs.scheduler.client')
    def test_cron_check_margin_level_sends_alert_when_low(self, mock_client, mock_bot):
        """cron_check_margin_level harus mengirim pesan Telegram saat free margin < 15%."""
        from backend.jobs.scheduler import cron_check_margin_level

        mock_client.futures_account.return_value = {
            'totalWalletBalance': '1000.0',
            'availableBalance': '100.0'  # 10% → di bawah 15% → harus alert
        }

        cron_check_margin_level()

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        self.assertEqual(call_args[0][0], 123456)
        self.assertIn("MARGIN TIPIS", call_args[0][1])

    # ────────────────────────────────────────────────────────────────
    # Skenario 3 [BARU]: cron_check_margin_level → TIDAK alert saat margin cukup
    # ────────────────────────────────────────────────────────────────
    @patch('backend.jobs.scheduler.bot')
    @patch('backend.jobs.scheduler.client')
    def test_cron_check_margin_level_no_alert_when_healthy(self, mock_client, mock_bot):
        """cron_check_margin_level TIDAK boleh mengirim alert jika margin > 15%."""
        from backend.jobs.scheduler import cron_check_margin_level

        mock_client.futures_account.return_value = {
            'totalWalletBalance': '1000.0',
            'availableBalance': '800.0'  # 80% → aman
        }

        cron_check_margin_level()
        mock_bot.send_message.assert_not_called()

    # ────────────────────────────────────────────────────────────────
    # Skenario 4 [BARU]: cron_check_api_health → alert dikirim saat API gagal
    # ────────────────────────────────────────────────────────────────
    @patch('backend.jobs.scheduler.bot')
    @patch('backend.jobs.scheduler.ALLOWED_USER_ID', 123456)
    @patch('backend.jobs.scheduler.client')
    def test_cron_check_api_health_sends_alert_on_failure(self, mock_client, mock_bot):
        """cron_check_api_health harus mengirim alert ke Telegram jika ping gagal."""
        from backend.jobs.scheduler import cron_check_api_health

        mock_client.futures_ping.side_effect = Exception("Connection timeout")

        cron_check_api_health()

        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        self.assertEqual(call_args[0][0], 123456)
        self.assertIn("PERINGATAN KONEKSI API", call_args[0][1])

    # ────────────────────────────────────────────────────────────────
    # Skenario 5 [BARU]: cron_check_api_health → TIDAK alert saat API sehat
    # ────────────────────────────────────────────────────────────────
    @patch('backend.jobs.scheduler.bot')
    @patch('backend.jobs.scheduler.client')
    def test_cron_check_api_health_no_alert_when_healthy(self, mock_client, mock_bot):
        """cron_check_api_health TIDAK boleh mengirim alert jika ping berhasil."""
        from backend.jobs.scheduler import cron_check_api_health

        mock_client.futures_ping.return_value = {}  # Ping sukses

        cron_check_api_health()
        mock_bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
