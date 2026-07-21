import re

def parse_signal(signal_text):
    """Mengekstrak data koin, tipe posisi, entry, SL, TP, kustom risiko, serta Confidence Score dari sinyal."""
    try:
        symbol = re.search(r'Symbol:\s*([A-Z0-9]+)', signal_text, re.IGNORECASE).group(1)
        side = "SELL" if "Short" in signal_text else "BUY"
        entry = float(re.search(r'Entry:\s*([0-9.]+)', signal_text).group(1))
        sl = float(re.search(r'SL:\s*([0-9.]+)', signal_text).group(1))
        tp1 = float(re.search(r'TP1:\s*([0-9.]+)', signal_text).group(1))
        tp2 = float(re.search(r'TP2:\s*([0-9.]+)', signal_text).group(1))
        tp3 = float(re.search(r'TP3:\s*([0-9.]+)', signal_text).group(1))
        
        # Ekstrak kustom risiko jika ada (misal: "Risk: 1%" atau "Risk: 2")
        risk_match = re.search(r'Risk:\s*([0-9.]+)%?', signal_text, re.IGNORECASE)
        risk = None
        if risk_match:
            val = float(risk_match.group(1))
            risk = val / 100.0 if val >= 0.1 else val
            
        # Ekstrak Confidence Score (AI) jika ada (misal: "Confidence Score (AI): 45%")
        confidence_match = re.search(r'Confidence\s*Score.*?:\s*([0-9.]+)%', signal_text, re.IGNORECASE)
        confidence = None
        if confidence_match:
            confidence = float(confidence_match.group(1))
            
        return {
            "symbol": symbol, "side": side, "entry": entry, "sl": sl,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "risk": risk, "confidence": confidence
        }
    except Exception as e:
        return None
