import time
from backend.config import ALLOWED_USER_ID, client, FIXED_LEVERAGE
from backend.services.binance_rest import execute_trade
from backend.bot.parser import parse_signal
from backend.db.repository import get_active_trades, get_performance_summary, get_trade_history, finalize_trade, get_config, set_config, get_all_configs
from backend.logger import logger
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Tempat penyimpanan sementara sinyal yang membutuhkan konfirmasi manual
PENDING_CONFIRMATIONS = {}

def register_handlers(bot):
    """Mendaftarkan handler pesan dan callback query ke instance Telegram Bot."""
    
    @bot.message_handler(content_types=['text', 'photo'])
    def handle_incoming_signal(message):
        text = message.text or message.caption or ""
        logger.info(f"Pesan masuk dari Telegram User ID {message.from_user.id} (@{message.from_user.username}): {text}")
        
        # Verifikasi pengirim (Keamanan)
        if message.from_user.id != ALLOWED_USER_ID:
            logger.warning(f"Akses ditolak untuk Telegram User ID {message.from_user.id}.")
            bot.reply_to(message, "⛔ Anda tidak diizinkan menggunakan bot ini.")
            return

        # 1. Perintah interaktif: Status Posisi (Upgraded dengan PRD-V2 DB)
        if text.startswith("/status") or text.startswith("/positions"):
            logger.info("Perintah /status diproses.")
            try:
                pos_info = client.futures_position_information()
                active_pos = [p for p in pos_info if float(p['positionAmt']) != 0]
                
                if not active_pos:
                    bot.reply_to(message, "ℹ️ Tidak ada posisi aktif saat ini di Binance Futures.")
                    return
                
                # Integrasi data active_trades dari DB SQLite PRD-V2
                db_trades = {t['symbol']: t for t in get_active_trades()}
                
                msg_lines = ["📊 *POSISI AKTIF BINANCE FUTURES:*"]
                for p in active_pos:
                    symbol = p['symbol']
                    side = "🟢 LONG" if float(p['positionAmt']) > 0 else "🔴 SHORT"
                    size = abs(float(p['positionAmt']))
                    entry = float(p['entryPrice'])
                    mark = float(p['markPrice'])
                    pnl = float(p['unRealizedProfit'])
                    leverage = FIXED_LEVERAGE
                    
                    db_info = db_trades.get(symbol)
                    stage_str = f"TP Stage {db_info['tp_stage']}" if db_info else "Entry"
                    rem_qty = db_info['remaining_qty'] if db_info else size
                    
                    msg_lines.append(
                        f"\n🪙 *{symbol}* ({side})\n"
                        f"• Status: `{stage_str}` | Remaining: `{rem_qty}`\n"
                        f"• Size: `{size}` (Leverage `{leverage}x`)\n"
                        f"• Entry: `{entry}` | Mark: `{mark}`\n"
                        f"• Unrealized PnL: `{pnl:+.2f} USDT`"
                    )
                bot.reply_to(message, "\n".join(msg_lines), parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Gagal memuat status posisi: {e}", exc_info=True)
                bot.reply_to(message, f"❌ Gagal memuat posisi: {e}")
            return

        # 2. Perintah interaktif: Rekapitulasi Performa (/summary / /performance)
        elif text.startswith("/summary") or text.startswith("/performance"):
            logger.info("Perintah /summary diproses.")
            try:
                summary = get_performance_summary()
                if not summary or not summary.get('total_trades'):
                    bot.reply_to(message, "ℹ️ Belum ada riwayat transaksi tercatat di jurnal performa.")
                    return
                    
                total = summary['total_trades']
                win = summary['winning_trades'] or 0
                loss = summary['losing_trades'] or 0
                winrate = (win / total * 100) if total > 0 else 0.0
                
                gross_pnl = summary['total_gross_pnl'] or 0.0
                commission = summary['total_commission'] or 0.0
                funding = summary['total_funding'] or 0.0
                net_pnl = summary['total_net_pnl'] or 0.0
                
                net_emoji = "🟢" if net_pnl >= 0 else "🔴"
                
                msg_summary = (
                    f"📊 *REKAPITULASI PERFORMA TRADING (PRD-V2)*\n\n"
                    f"• Total Sinyal: `{total}` Trade\n"
                    f"• Win Rate: `{winrate:.1f}%` (`{win}` Win / `{loss}` Loss)\n\n"
                    f"💰 *Detail Keuangan (USD):*\n"
                    f"• Gross PnL (Kotor): `${gross_pnl:+.2f}`\n"
                    f"• Est. Komisi Binance: `-${commission:.2f}`\n"
                    f"• Est. Funding Fee: `${funding:+.2f}`\n\n"
                    f"{net_emoji} *NET PnL BERSIH: `${net_pnl:+.2f} USDT`*"
                )
                bot.reply_to(message, msg_summary, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Gagal memuat summary performa: {e}", exc_info=True)
                bot.reply_to(message, f"❌ Gagal memuat summary performa: {e}")
            return

        # 3. Perintah interaktif: Riwayat Trade Terakhir (/history)
        elif text.startswith("/history"):
            logger.info("Perintah /history diproses.")
            try:
                history = get_trade_history(limit=5)
                if not history:
                    bot.reply_to(message, "ℹ️ Belum ada riwayat trade tertutup di database.")
                    return
                    
                msg_lines = ["📜 *RIWAYAT 5 TRADE TERAKHIR:*"]
                for t in history:
                    symbol = t['symbol']
                    side = "🟢 LONG" if t['side'] == "BUY" else "🔴 SHORT"
                    close_reason = t['close_reason']
                    net_pnl = t['net_pnl_usd']
                    pnl_pct = t['net_pnl_percent']
                    pnl_emoji = "📈" if net_pnl >= 0 else "📉"
                    
                    msg_lines.append(
                        f"\n🪙 *{symbol}* ({side})\n"
                        f"• Status: `{close_reason}` ({t['duration_minutes'] or 0}m)\n"
                        f"• Entry: `{t['entry_price']}` | Close: `{t['close_price']}`\n"
                        f"• {pnl_emoji} Net PnL: `${net_pnl:+.2f}` (`{pnl_pct:+.1f}% ROE`)"
                    )
                bot.reply_to(message, "\n".join(msg_lines), parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Gagal memuat history trade: {e}", exc_info=True)
                bot.reply_to(message, f"❌ Gagal memuat history trade: {e}")
            return

        # 4. Perintah interaktif: Paksa Tutup Posisi
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
                res = client.futures_create_order(symbol=symbol, side=side, type='MARKET', quantity=qty, reduceOnly=True)
                close_order_id = res['orderId']
                
                client.futures_cancel_all_open_orders(symbol=symbol)
                try: client.futures_cancel_all_algo_open_orders(symbol=symbol)
                except Exception: pass
                
                # Beri jeda 500ms agar engine Binance memperbarui riwayat trade
                time.sleep(0.5)
                
                # Ambil detail eksekusi trade penutupan
                fill_price = 0.0
                realized_pnl = 0.0
                fee = 0.0
                try:
                    trades = client.futures_account_trades(symbol=symbol, limit=10)
                    matching_trades = [t for t in trades if t['orderId'] == close_order_id]
                    if matching_trades:
                        total_qty = sum(float(t['qty']) for t in matching_trades)
                        weighted_price_sum = sum(float(t['price']) * float(t['qty']) for t in matching_trades)
                        fill_price = weighted_price_sum / total_qty if total_qty > 0 else float(matching_trades[0]['price'])
                        realized_pnl = sum(float(t['realizedPnl']) for t in matching_trades)
                        fee = sum(float(t['commission']) for t in matching_trades)
                except Exception as err:
                    print(f"[WARN] Gagal mengambil detail close trade: {err}")
                
                emoji_pnl = "📈" if realized_pnl >= 0 else "📉"
                pnl_str = f"{realized_pnl:+.4f} USDT" if realized_pnl != 0 else "0.00 USDT"
                
                msg_close = (
                    f"✅ *Berhasil Menutup Posisi {symbol}*\n\n"
                    f"📊 *Rincian Penutupan:*\n"
                    f"• Tipe: `MARKET {side}`\n"
                    f"• Size: `{qty}`\n"
                    f"• Close Price: `{fill_price:.4f}`\n"
                    f"• {emoji_pnl} Realized PnL: `{pnl_str}`\n"
                    f"• Fee Komisi: `{fee:.4f} USDT`\n\n"
                    f"🛡️ Semua pending orders (termasuk stop loss) berhasil dibersihkan."
                )
                bot.reply_to(message, msg_close, parse_mode="Markdown")
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

        # 4. Perintah interaktif: Manajemen Risiko & Daily Anchor Balance (/risk, /set_risk, /reset_anchor)
        elif text.startswith("/risk") or text.startswith("/reset_anchor") or text.startswith("/set_risk"):
            try:
                if text.startswith("/reset_anchor"):
                    # Reset Daily Anchor Balance manual ke Total Account Equity saat ini
                    account_info = client.futures_account()
                    avail_balance = float([a['availableBalance'] for a in account_info['assets'] if a['asset'] == 'USDT'][0])
                    pos_info = client.futures_position_information()
                    total_initial_margin = sum(abs(float(p['positionAmt'])) * float(p['entryPrice']) / 15.0 for p in pos_info if float(p['positionAmt']) != 0)
                    total_equity = avail_balance + total_initial_margin
                    
                    set_config("daily_anchor_balance", total_equity)
                    bot.reply_to(message, f"🔄 *Daily Anchor Balance Berhasil Di-reset!*\n\nAcuan saldo harian baru: `${total_equity:.2f} USDT`", parse_mode="Markdown")
                    return

                elif text.startswith("/set_risk"):
                    parts = text.split()
                    if len(parts) < 2:
                        bot.reply_to(message, "⚠️ Format salah.\nGunakan: `/set_risk [PERSEN]` (Contoh: `/set_risk 2.0` untuk 2%)\nAtau: `/set_risk fixed [USD]` (Contoh: `/set_risk fixed 2.5` untuk $2.5)", parse_mode="Markdown")
                        return
                    if parts[1].lower() == "fixed" and len(parts) >= 3:
                        val = float(parts[2])
                        set_config("risk_mode", "FIXED_USD")
                        set_config("fixed_risk_usd", val)
                        bot.reply_to(message, f"✅ Mode risiko diubah ke *FIXED USD*: `${val:.2f} USDT` per trade.", parse_mode="Markdown")
                    else:
                        pct = float(parts[1]) / 100.0
                        set_config("risk_mode", "DAILY_ANCHOR")
                        set_config("risk_pct", pct)
                        bot.reply_to(message, f"✅ Mode risiko diubah ke *DAILY ANCHOR*: `{float(parts[1]):.1f}%` per trade.", parse_mode="Markdown")
                    return

                # Default /risk: Tampilkan info status risiko
                configs = get_all_configs()
                mode = configs.get("risk_mode", "DAILY_ANCHOR")
                pct = float(configs.get("risk_pct", "0.02")) * 100
                anchor = float(configs.get("daily_anchor_balance", "0.0"))
                fixed_val = configs.get("fixed_risk_usd", "2.0")
                
                account_info = client.futures_account()
                avail_balance = float([a['availableBalance'] for a in account_info['assets'] if a['asset'] == 'USDT'][0])
                pos_info = client.futures_position_information()
                total_initial_margin = sum(abs(float(p['positionAmt'])) * float(p['entryPrice']) / 15.0 for p in pos_info if float(p['positionAmt']) != 0)
                total_equity = avail_balance + total_initial_margin

                msg_risk = (
                    f"⚙️ *KONFIGURASI MANAJEMEN RISIKO BOT:*\n\n"
                    f"• Mode Risiko: `{mode}`\n"
                    f"• Target Risiko: `{pct:.1f}%` per trade" + (f" (Fixed `${fixed_val}`)" if mode == "FIXED_USD" else "") + "\n"
                    f"• Daily Anchor Balance: `${anchor:.2f} USDT`\n"
                    f"• Available Free Margin: `${avail_balance:.2f} USDT`\n"
                    f"• Total Wallet Equity: `${total_equity:.2f} USDT`\n\n"
                    f"💡 *Perintah Pengaturan:*\n"
                    f"• `/set_risk 2.0` -> Ubah % risiko harian\n"
                    f"• `/set_risk fixed 2.5` -> Ubah nominal fixed USD\n"
                    f"• `/reset_anchor` -> Reset saldo jangkar ke Equity terkini (`${total_equity:.2f}`)"
                )
                bot.reply_to(message, msg_risk, parse_mode="Markdown")
            except Exception as err:
                logger.error(f"Gagal memproses command /risk: {err}", exc_info=True)
                bot.reply_to(message, f"❌ Error: {err}")
            return

        # Helper function untuk memproses eksekusi trade dan menangani batasan quantity / margin
        def process_trade_execution(data, msg_target=message):
            result_msg = execute_trade(data)
            
            if isinstance(result_msg, str) and result_msg.startswith("MARGIN_EXCEEDS_AVAILABLE:"):
                parts = result_msg.split(":")
                req_margin = float(parts[1])
                avail_bal = float(parts[2])
                max_qty = float(parts[3])
                
                unique_id = str(int(time.time() * 1000))
                data_copy = dict(data)
                data_copy['override_qty'] = max_qty
                PENDING_CONFIRMATIONS[unique_id] = data_copy
                
                markup = InlineKeyboardMarkup()
                btn_yes = InlineKeyboardButton(f"✅ YES - Gunakan Sisa Saldo (${avail_bal:.2f})", callback_data=f"exec_qty_{unique_id}")
                btn_no = InlineKeyboardButton("❌ NO - Batalkan Trade", callback_data=f"cancel_qty_{unique_id}")
                markup.row(btn_yes)
                markup.row(btn_no)
                
                alert_text = (
                    f"⚠️ *PERINGATAN KECUKUPAN MARGIN (Binance)*\n\n"
                    f"Margin yang dibutuhkan untuk *{data['symbol']}* (`${req_margin:.2f} USDT`) melebihi Saldo Bebas yang tersedia (`${avail_bal:.2f} USDT`).\n\n"
                    f"Apakah Anda ingin menyesuaikan kuantitas dan menggunakan seluruh sisa saldo bebas (`${avail_bal:.2f} USDT`)?"
                )
                bot.reply_to(msg_target, alert_text, reply_markup=markup, parse_mode="Markdown")

            elif isinstance(result_msg, str) and (result_msg.startswith("QTY_UNDER_MIN:") or result_msg.startswith("QTY_OVER_MAX:")):
                parts = result_msg.split(":")
                err_type = parts[0]
                calculated_qty = float(parts[1])
                target_qty = float(parts[2])
                
                unique_id = str(int(time.time() * 1000))
                data_copy = dict(data)
                data_copy['override_qty'] = target_qty
                PENDING_CONFIRMATIONS[unique_id] = data_copy
                
                markup = InlineKeyboardMarkup()
                btn_yes = InlineKeyboardButton(f"✅ Gunakan {target_qty}", callback_data=f"exec_qty_{unique_id}")
                btn_no = InlineKeyboardButton("❌ Batalkan Trade", callback_data=f"cancel_qty_{unique_id}")
                markup.row(btn_yes, btn_no)
                
                if err_type == "QTY_UNDER_MIN":
                    alert_text = (
                        f"⚠️ *PERINGATAN KUANTITAS MINIMUM (Binance)*\n\n"
                        f"Kuantitas terhitung untuk *{data['symbol']}* (`{calculated_qty}`) lebih kecil dari batas minimum Binance (`{target_qty}`).\n\n"
                        f"Apakah Anda ingin tetap mengeksekusi dengan kuantitas minimum (`{target_qty}`)?"
                    )
                else:
                    alert_text = (
                        f"⚠️ *PERINGATAN KUANTITAS MAKSIMUM (Binance)*\n\n"
                        f"Kuantitas terhitung untuk *{data['symbol']}* (`{calculated_qty}`) melebihi batas maksimum Binance (`{target_qty}`).\n\n"
                        f"Apakah Anda ingin menyesuaikan ke kuantitas maksimum (`{target_qty}`)?"
                    )
                bot.reply_to(msg_target, alert_text, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.reply_to(msg_target, result_msg, parse_mode="Markdown")

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
                process_trade_execution(parsed_data, message)
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
        if data.startswith("exec_qty_"):
            unique_id = data.replace("exec_qty_", "")
            if unique_id in PENDING_CONFIRMATIONS:
                parsed_data = PENDING_CONFIRMATIONS.pop(unique_id)
                bot.answer_callback_query(call.id, "Mengeksekusi trade dengan penyesuaian qty...")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"⏳ *Penyesuaian Kuantitas Diterima.* Mengeksekusi trade {parsed_data['symbol']} (Qty: `{parsed_data['override_qty']}`)...",
                    parse_mode="Markdown"
                )
                result_msg = execute_trade(parsed_data)
                bot.send_message(call.message.chat.id, result_msg, parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "❌ Sinyal sudah kedaluwarsa atau telah diproses.", show_alert=True)

        elif data.startswith("cancel_qty_"):
            unique_id = data.replace("cancel_qty_", "")
            PENDING_CONFIRMATIONS.pop(unique_id, None)
            bot.answer_callback_query(call.id, "Eksekusi dibatalkan.")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ *Eksekusi trade dibatalkan karena penyesuaian kuantitas ditolak.*",
                parse_mode="Markdown"
            )

        elif data.startswith("exec_"):
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
                
                # Eksekusi trade dan kirimkan hasilnya (dengan penanganan penyesuaian qty)
                result_msg = execute_trade(parsed_data)
                if isinstance(result_msg, str) and (result_msg.startswith("QTY_UNDER_MIN:") or result_msg.startswith("QTY_OVER_MAX:")):
                    parts = result_msg.split(":")
                    err_type = parts[0]
                    calculated_qty = float(parts[1])
                    target_qty = float(parts[2])
                    
                    new_id = str(int(time.time() * 1000))
                    parsed_data['override_qty'] = target_qty
                    PENDING_CONFIRMATIONS[new_id] = parsed_data
                    
                    markup = InlineKeyboardMarkup()
                    btn_yes = InlineKeyboardButton(f"✅ Gunakan {target_qty}", callback_data=f"exec_qty_{new_id}")
                    btn_no = InlineKeyboardButton("❌ Batalkan Trade", callback_data=f"cancel_qty_{new_id}")
                    markup.row(btn_yes, btn_no)
                    
                    if err_type == "QTY_UNDER_MIN":
                        alert_text = (
                            f"⚠️ *PERINGATAN KUANTITAS MINIMUM (Binance)*\n\n"
                            f"Kuantitas terhitung untuk *{parsed_data['symbol']}* (`{calculated_qty}`) lebih kecil dari batas minimum Binance (`{target_qty}`).\n\n"
                            f"Apakah Anda ingin tetap mengeksekusi dengan kuantitas minimum (`{target_qty}`)?"
                        )
                    else:
                        alert_text = (
                            f"⚠️ *PERINGATAN KUANTITAS MAKSIMUM (Binance)*\n\n"
                            f"Kuantitas terhitung untuk *{parsed_data['symbol']}* (`{calculated_qty}`) melebihi batas maksimum Binance (`{target_qty}`).\n\n"
                            f"Apakah Anda ingin menyesuaikan ke kuantitas maksimum (`{target_qty}`)?"
                        )
                    bot.send_message(call.message.chat.id, alert_text, reply_markup=markup, parse_mode="Markdown")
                else:
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
