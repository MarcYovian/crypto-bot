import re
import time
from config import ALLOWED_USER_ID, client, FIXED_LEVERAGE
from services.binance_service import execute_trade
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Tempat penyimpanan sementara sinyal yang membutuhkan konfirmasi manual
PENDING_CONFIRMATIONS = {}

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

def register_handlers(bot):
    """Mendaftarkan handler pesan dan callback query ke instance Telegram Bot."""
    
    @bot.message_handler(content_types=['text', 'photo'])
    def handle_incoming_signal(message):
        text = message.text or message.caption or ""
        print(f"[Telegram] Pesan masuk dari {message.from_user.id} ({message.from_user.username}): {text}")
        
        # Verifikasi pengirim (Keamanan)
        if message.from_user.id != ALLOWED_USER_ID:
            bot.reply_to(message, "⛔ Anda tidak diizinkan menggunakan bot ini.")
            return

        # 1. Perintah interaktif: Status Posisi
        if text.startswith("/status") or text.startswith("/positions"):
            try:
                pos_info = client.futures_position_information()
                active_pos = [p for p in pos_info if float(p['positionAmt']) != 0]
                
                if not active_pos:
                    bot.reply_to(message, "ℹ️ Tidak ada posisi aktif saat ini di Binance Futures.")
                    return
                
                msg_lines = ["📊 *POSISI AKTIF BINANCE FUTURES:*"]
                for p in active_pos:
                    symbol = p['symbol']
                    side = "🟢 LONG" if float(p['positionAmt']) > 0 else "🔴 SHORT"
                    size = abs(float(p['positionAmt']))
                    entry = float(p['entryPrice'])
                    mark = float(p['markPrice'])
                    pnl = float(p['unRealizedProfit'])
                    leverage = FIXED_LEVERAGE
                    
                    msg_lines.append(
                        f"\n🪙 *{symbol}* ({side})\n"
                        f"• Size: `{size}` (Leverage `{leverage}x`)\n"
                        f"• Entry: `{entry}` | Mark: `{mark}`\n"
                        f"• Unrealized PnL: `{pnl:+.2f} USDT`"
                    )
                bot.reply_to(message, "\n".join(msg_lines), parse_mode="Markdown")
            except Exception as e:
                bot.reply_to(message, f"❌ Gagal memuat posisi: {e}")
            return

        # 2. Perintah interaktif: Paksa Tutup Posisi
        elif text.startswith("/close"):
            parts = text.split()
            if len(parts) < 2:
                bot.reply_to(message, "⚠️ Format salah. Gunakan: `/close [SYMBOL]` (Contoh: `/close BTCUSDT`)", parse_mode="Markdown")
                return
            symbol = parts[1].upper()
            try:
                pos_info = client.futures_position_information(symbol=symbol)
                position_amt = float(pos_info[0]['positionAmt']) if pos_info else 0
                
                if position_amt == 0:
                    bot.reply_to(message, f"ℹ️ Tidak ada posisi aktif untuk {symbol}.")
                    return
                
                # Eksekusi market order penutupan kebalikannya
                side = "SELL" if position_amt > 0 else "BUY"
                qty = abs(position_amt)
                
                client.futures_create_order(symbol=symbol, side=side, type='MARKET', quantity=qty, reduceOnly=True)
                client.futures_cancel_all_open_orders(symbol=symbol)
                try: client.futures_cancel_all_algo_open_orders(symbol=symbol)
                except Exception: pass
                
                bot.reply_to(message, f"✅ Posisi *{symbol}* berhasil ditutup dan semua sisa order dibatalkan.", parse_mode="Markdown")
            except Exception as e:
                bot.reply_to(message, f"❌ Gagal menutup posisi {symbol}: {e}")
            return

        # 3. Perintah interaktif: Batalkan Semua Order Pending
        elif text.startswith("/cancel"):
            parts = text.split()
            if len(parts) < 2:
                bot.reply_to(message, "⚠️ Format salah. Gunakan: `/cancel [SYMBOL]` (Contoh: `/cancel BTCUSDT`)", parse_mode="Markdown")
                return
            symbol = parts[1].upper()
            try:
                client.futures_cancel_all_open_orders(symbol=symbol)
                try: client.futures_cancel_all_algo_open_orders(symbol=symbol)
                except Exception: pass
                bot.reply_to(message, f"✅ Semua pending orders untuk *{symbol}* berhasil dibatalkan.", parse_mode="Markdown")
            except Exception as e:
                bot.reply_to(message, f"❌ Gagal membatalkan order {symbol}: {e}")
            return

        # 4. Handle Sinyal Trading Otomatis
        if "Symbol:" in text and "Entry:" in text:
            parsed_data = parse_signal(text)
            if not parsed_data:
                bot.reply_to(message, "❌ Gagal mengekstrak data dari teks sinyal.")
                return

            confidence = parsed_data['confidence']
            
            # Jika Confidence Score di atas atau sama dengan 72%, langsung eksekusi tanpa konfirmasi
            if confidence is not None and confidence >= 72.0:
                bot.reply_to(message, f"🚀 *Confidence Score Tinggi ({confidence}%)*. Mengeksekusi trade langsung...", parse_mode="Markdown")
                result_msg = execute_trade(parsed_data)
                bot.reply_to(message, result_msg, parse_mode="Markdown")
            else:
                # Jika di bawah 72% atau tidak ada score, kirim tombol konfirmasi
                unique_id = str(int(time.time() * 1000))
                PENDING_CONFIRMATIONS[unique_id] = parsed_data
                
                score_str = f"{confidence}%" if confidence is not None else "Tidak Terdeteksi"
                
                markup = InlineKeyboardMarkup()
                btn_exec = InlineKeyboardButton("✅ Konfirmasi Eksekusi", callback_data=f"exec_{unique_id}")
                btn_cancel = InlineKeyboardButton("❌ Batalkan", callback_data=f"cancel_{unique_id}")
                markup.row(btn_exec, btn_cancel)
                
                bot.reply_to(
                    message,
                    f"⚠️ *PERINGATAN CONFIDENCE SCORE*\n\n"
                    f"Sinyal trading *{parsed_data['symbol']}* ({parsed_data['side']}) mendeteksi:\n"
                    f"• Confidence Score: `{score_str}` (Threshold aman: `72%`)\n\n"
                    f"Apakah Anda ingin tetap mengeksekusi sinyal ini?",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )

    # Handler untuk merespons klik tombol konfirmasi
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        # Keamanan: pastikan hanya allowed user yang bisa memicu eksekusi
        if call.from_user.id != ALLOWED_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Anda tidak diizinkan mengeksekusi perintah ini.", show_alert=True)
            return

        data = call.data
        if data.startswith("exec_"):
            unique_id = data.replace("exec_", "")
            if unique_id in PENDING_CONFIRMATIONS:
                parsed_data = PENDING_CONFIRMATIONS.pop(unique_id)
                
                # Update status pesan ke user
                bot.answer_callback_query(call.id, "Mengeksekusi trade...")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"⏳ *Konfirmasi Diterima.* Mengeksekusi trade {parsed_data['symbol']}...",
                    parse_mode="Markdown"
                )
                
                # Eksekusi trade dan kirimkan hasilnya
                result_msg = execute_trade(parsed_data)
                bot.send_message(call.message.chat.id, result_msg, parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "❌ Sinyal sudah kedaluwarsa atau telah diproses.", show_alert=True)
                
        elif data.startswith("cancel_"):
            unique_id = data.replace("cancel_", "")
            PENDING_CONFIRMATIONS.pop(unique_id, None)
            
            bot.answer_callback_query(call.id, "Eksekusi dibatalkan.")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ *Eksekusi sinyal dibatalkan oleh pengguna.*",
                parse_mode="Markdown"
            )
