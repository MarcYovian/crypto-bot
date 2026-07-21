import unittest
from backend.bot.parser import parse_signal

class TestSignalParser(unittest.TestCase):

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

    def test_parse_invalid_text(self):
        invalid_text = "Halo bot, tolong tampilkan harga BTC hari ini."
        data = parse_signal(invalid_text)
        self.assertIsNone(data)

if __name__ == "__main__":
    unittest.main()
