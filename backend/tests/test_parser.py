import unittest
from backend.bot.parser import parse_signal

class TestSignalParser(unittest.TestCase):

    # ────────────────────────────────────────────────────────────────
    # Skenario 1: AI Agent SHORT signal (sudah ada)
    # ────────────────────────────────────────────────────────────────
    def test_parse_ai_agent_short_signal(self):
        sample_signal = (
            "🤖 AI Agent Detect Chart Pattern\n\n"
            "🚨 Symbol: BTCUSDT 🔴 Short\n"
            "⏱ Timeframe: 1H\n"
            "📈 Leverage: 75x\n"
            "🔷 Pattern: Ranging Channel\n\n"
            "💰 Entry: 66770\n"
            "🛡 SL: 66900\n"
            "🎯 TP1: 66600(+95.93%)\n"
            "⚡️ TP2: 66500 (+287.80%)\n"
            "🔥 TP3: 66400 (+360.50%)\n"
        )
        data = parse_signal(sample_signal)
        self.assertIsNotNone(data)
        self.assertEqual(data['symbol'], "BTCUSDT")
        self.assertEqual(data['side'], "SELL")
        self.assertEqual(data['entry'], 66770.0)
        self.assertEqual(data['sl'], 66900.0)
        self.assertEqual(data['tp1'], 66600.0)
        self.assertEqual(data['tp2'], 66500.0)
        self.assertEqual(data['tp3'], 66400.0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 2: Standard LONG signal (sudah ada)
    # ────────────────────────────────────────────────────────────────
    def test_parse_standard_long_signal(self):
        sample_signal = (
            "🚀 SIGNAL BUY / LONG 🟢\n"
            "Symbol: SOLUSDT\n"
            "Entry: 145.50\n"
            "SL: 140.00\n"
            "TP1: 150.00\n"
            "TP2: 155.00\n"
            "TP3: 160.00\n"
        )
        data = parse_signal(sample_signal)
        self.assertIsNotNone(data)
        self.assertEqual(data['symbol'], "SOLUSDT")
        self.assertEqual(data['side'], "BUY")
        self.assertEqual(data['entry'], 145.50)
        self.assertEqual(data['sl'], 140.00)

    # ────────────────────────────────────────────────────────────────
    # Skenario 3: Input teks tidak valid (sudah ada)
    # ────────────────────────────────────────────────────────────────
    def test_parse_invalid_text(self):
        invalid_text = "Halo bot, tolong tampilkan harga BTC hari ini."
        data = parse_signal(invalid_text)
        self.assertIsNone(data)

    # ────────────────────────────────────────────────────────────────
    # Skenario 4 [BARU]: Sinyal dengan kustom Risk: 1.5%
    # ────────────────────────────────────────────────────────────────
    def test_parse_signal_with_custom_risk(self):
        """Verifikasi field 'risk' diekstrak dengan benar dari sinyal."""
        sample_signal = (
            "🔴 Short ETHUSDT\n"
            "Symbol: ETHUSDT\n"
            "Entry: 2500.0\n"
            "SL: 2550.0\n"
            "TP1: 2450.0\n"
            "TP2: 2400.0\n"
            "TP3: 2350.0\n"
            "Risk: 1.5%\n"
        )
        data = parse_signal(sample_signal)
        self.assertIsNotNone(data)
        self.assertEqual(data['side'], "SELL")
        self.assertIsNotNone(data['risk'])
        self.assertAlmostEqual(data['risk'], 0.015, places=4)

    # ────────────────────────────────────────────────────────────────
    # Skenario 5 [BARU]: Sinyal dengan Confidence Score AI
    # ────────────────────────────────────────────────────────────────
    def test_parse_signal_with_confidence_score(self):
        """Verifikasi field 'confidence' diekstrak dengan benar dari sinyal."""
        sample_signal = (
            "🤖 AI Agent Detect Chart Pattern\n\n"
            "🚨 Symbol: ADAUSDT 🟢 Long\n"
            "💰 Entry: 0.55\n"
            "🛡 SL: 0.52\n"
            "🎯 TP1: 0.58\n"
            "⚡️ TP2: 0.61\n"
            "🔥 TP3: 0.64\n"
            "Confidence Score (AI): 85%\n"
        )
        data = parse_signal(sample_signal)
        self.assertIsNotNone(data)
        self.assertEqual(data['side'], "BUY")
        self.assertIsNotNone(data['confidence'])
        self.assertEqual(data['confidence'], 85.0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 6 [BARU]: Sinyal dengan field risk DAN confidence sekaligus
    # ────────────────────────────────────────────────────────────────
    def test_parse_signal_risk_and_confidence_combined(self):
        """Verifikasi sinyal dengan risk + confidence score sekaligus."""
        sample_signal = (
            "🔴 Short XRPUSDT\n"
            "Symbol: XRPUSDT\n"
            "Entry: 0.60\n"
            "SL: 0.63\n"
            "TP1: 0.57\n"
            "TP2: 0.54\n"
            "TP3: 0.51\n"
            "Risk: 2%\n"
            "Confidence Score (AI): 72%\n"
        )
        data = parse_signal(sample_signal)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(data['risk'], 0.02, places=4)
        self.assertEqual(data['confidence'], 72.0)

    # ────────────────────────────────────────────────────────────────
    # Skenario 7 [BARU]: Sinyal dengan TP2/TP3 tidak ada (incomplete signal)
    # ────────────────────────────────────────────────────────────────
    def test_parse_incomplete_signal_returns_none(self):
        """Sinyal tanpa TP2 dan TP3 harus return None (tidak bisa diproses)."""
        incomplete_signal = (
            "🟢 BUY BNBUSDT\n"
            "Symbol: BNBUSDT\n"
            "Entry: 300.0\n"
            "SL: 290.0\n"
            "TP1: 310.0\n"
            # TP2 dan TP3 sengaja tidak ada
        )
        data = parse_signal(incomplete_signal)
        self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()
