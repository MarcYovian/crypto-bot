import time
import json
import threading
from binance import BinanceSocketManager
from backend.config import BINANCE_API_KEY, BINANCE_API_SECRET, client, bot, ALLOWED_USER_ID, FIXED_LEVERAGE
from backend.db.repository import get_active_trades, deactivate_trade, update_tp_stage, update_trade_orders, record_partial_close, finalize_trade
from backend.services.binance_rest import get_symbol_info
from backend.core.risk_manager import round_step
from backend.logger import logger

class BinanceWebSocketManager:
    """Mengelola koneksi WebSocket User Data Stream Binance Futures secara real-time."""
    
    def __init__(self):
        self.bsm = None
        self.listen_key = None
        self.keep_alive_thread = None
        self.is_running = False

    def handle_user_data_message(self, message):
        """Callback handler untuk menerima push event dari Binance User Data Stream."""
        try:
            if isinstance(message, str):
                message = json.loads(message)
                
            if not isinstance(message, dict):
                return
                
            event_type = message.get("e")
            
            # Event Update Order & Trade (Real-time Execution)
            if event_type == "ORDER_TRADE_UPDATE":
                order_data = message.get("o", {})
                symbol = order_data.get("s")
                side = order_data.get("S")
                order_type = order_data.get("ot")
                status = order_data.get("X")  # FILLED, NEW, CANCELED, dll
                order_id = str(order_data.get("i"))
                executed_price = float(order_data.get("ap", 0) or order_data.get("p", 0))
                
                logger.info(f"[WS EVENT] ORDER_TRADE_UPDATE [{symbol}]: OrderID={order_id}, Status={status}, Type={order_type}, Price={executed_price}")
                
                if status == "FILLED":
                    self._process_filled_order(symbol, side, order_id, executed_price, order_type)
                    
        except Exception as e:
            logger.error(f"[WS ERROR] Gagal memproses data pesan WebSocket: {e}", exc_info=True)

    def _process_filled_order(self, symbol, side, order_id, executed_price, order_type):
        """Memproses logika trailing Stop Loss & notifikasi ketika order TP/SL terisi secara instant."""
        active_trades = get_active_trades()
        matching_trade = None
        
        for trade in active_trades:
            if trade['symbol'] == symbol:
                matching_trade = trade
                break
                
        if not matching_trade:
            return
            
        db_id = matching_trade['id']
        tr_side = matching_trade['side']
        entry = matching_trade['entry_price']
        sl = matching_trade['sl_price']
        tp1 = matching_trade['tp1_price']
        tp2 = matching_trade['tp2_price']
        tp3 = matching_trade['tp3_price']
        tp_stage = matching_trade['tp_stage']
        sl_order_id = matching_trade['sl_order_id']
        tp1_order_id = matching_trade['tp1_order_id']
        tp2_order_id = matching_trade['tp2_order_id']
        tp3_order_id = matching_trade['tp3_order_id']
         
        tick_size, step_size, min_qty, max_qty = get_symbol_info(symbol)

        # 1. TP1 Terisi (FILLED) -> Pindahkan SL ke Entry Price (Breakeven)
        if tp1_order_id and order_id == str(tp1_order_id) and tp_stage < 1:
            logger.info(f"[WS EVENT] TP1 Terisi untuk {symbol} @ {executed_price}. Memindahkan SL ke Entry...")
            if sl_order_id:
                try: client.futures_cancel_algo_order(symbol=symbol, algoId=sl_order_id)
                except Exception: pass
                
            sl_side = "BUY" if tr_side == "SELL" else "SELL"
            new_sl_price = round_step(entry, tick_size)
            new_sl_res = client.futures_create_order(
                symbol=symbol, side=sl_side, type='STOP_MARKET', stopPrice=new_sl_price, closePosition=True
            )
            new_sl_id = str(new_sl_res.get('orderId') or new_sl_res.get('algoId'))
            
            # Hitung profit nominal TP1 & update database
            initial_qty = matching_trade['initial_qty']
            qty_tp1 = round_step(initial_qty * 0.50, step_size)
            pnl1 = qty_tp1 * abs(executed_price - entry)
            
            record_partial_close(
                trade_id=db_id, event_type='TP1_HIT', exit_price=executed_price,
                qty_closed=qty_tp1, realized_pnl_usd=pnl1
            )
            update_trade_orders(db_id, sl_order_id=new_sl_id)
            
            bot.send_message(
                ALLOWED_USER_ID,
                f"🎉 *[{symbol}] Target TP1 Terpenuhi (via WebSocket)!*\n"
                f"• Harga Eksekusi TP1: `{executed_price}`\n"
                f"• Profit Direalisasi: `+{pnl1:.2f} USDT`\n"
                f"• Stop Loss otomatis dipindahkan ke *Entry Price* (`{new_sl_price}`).\n"
                f"• Posisi saat ini bebas risiko (Risk-Free).",
                parse_mode="Markdown"
            )

        # 2. TP2 Terisi (FILLED) -> Pindahkan SL ke TP1 Price
        elif tp2_order_id and order_id == str(tp2_order_id) and tp_stage < 2:
            logger.info(f"[WS EVENT] TP2 Terisi untuk {symbol} @ {executed_price}. Memindahkan SL ke TP1...")
            if sl_order_id:
                try: client.futures_cancel_algo_order(symbol=symbol, algoId=sl_order_id)
                except Exception: pass
                
            sl_side = "BUY" if tr_side == "SELL" else "SELL"
            new_sl_price = round_step(tp1, tick_size)
            new_sl_res = client.futures_create_order(
                symbol=symbol, side=sl_side, type='STOP_MARKET', stopPrice=new_sl_price, closePosition=True
            )
            new_sl_id = str(new_sl_res.get('orderId') or new_sl_res.get('algoId'))
            
            # Hitung profit nominal TP2 & update database
            initial_qty = matching_trade['initial_qty']
            qty_tp2 = round_step(initial_qty * 0.25, step_size)
            pnl2 = qty_tp2 * abs(executed_price - entry)
            
            record_partial_close(
                trade_id=db_id, event_type='TP2_HIT', exit_price=executed_price,
                qty_closed=qty_tp2, realized_pnl_usd=pnl2
            )
            update_trade_orders(db_id, sl_order_id=new_sl_id)
            
            bot.send_message(
                ALLOWED_USER_ID,
                f"🎉 *[{symbol}] Target TP2 Terpenuhi (via WebSocket)!*\n"
                f"• Harga Eksekusi TP2: `{executed_price}`\n"
                f"• Profit Direalisasi: `+{pnl2:.2f} USDT`\n"
                f"• Stop Loss otomatis dipindahkan ke *TP1 Price* (`{new_sl_price}`).",
                parse_mode="Markdown"
            )

        # 3. TP3 Terisi (FILLED) -> Tutup Posisi Penuh & Finalize Trade
        elif tp3_order_id and order_id == str(tp3_order_id) and tp_stage < 3:
            logger.info(f"[WS EVENT] TP3 Terisi untuk {symbol} @ {executed_price}. Menutup Trade...")
            summary = finalize_trade(db_id, close_price=executed_price, close_reason="FULL_TP")
            
            pnl_info = f"\n💰 *Net PnL Bersih:* `+${summary['net_pnl_usd']:.2f}` (`+{summary['net_pnl_percent']:.2f}%` ROE)" if summary else ""
            bot.send_message(
                ALLOWED_USER_ID,
                f"🏁 *[{symbol}] Target TP3 Terpenuhi (via WebSocket)!*\n"
                f"• Harga Eksekusi TP3: `{executed_price}`{pnl_info}\n"
                f"• Posisi telah ditutup penuh dengan profit maksimal.",
                parse_mode="Markdown"
            )

        # 4. Stop Loss Terisi (FILLED) -> Finalize Trade di DB
        elif sl_order_id and order_id == str(sl_order_id):
            logger.info(f"[WS EVENT] Stop Loss Terisi untuk {symbol} @ {executed_price}. Deaktivasi Trade...")
            close_reason = "TP1_BEP_SL" if tp_stage == 1 else "TP2_BEP_SL" if tp_stage == 2 else "SL_HIT"
            summary = finalize_trade(db_id, close_price=executed_price, close_reason=close_reason)
            
            pnl_info = f"\n📊 *Hasil Akhir (Net PnL):* `${summary['net_pnl_usd']:+.2f}` (`{summary['net_pnl_percent']:+.2f}%` ROE)" if summary else ""
            bot.send_message(
                ALLOWED_USER_ID,
                f"🛡️ *[{symbol}] Stop Loss Tersentuh ({close_reason})* di harga `{executed_price}`.{pnl_info}\n"
                f"• Posisi telah ditutup dan dirapikan di jurnal database.",
                parse_mode="Markdown"
            )

    def _keep_alive_listen_key(self):
        """Memperbarui listenKey setiap 30 menit agar koneksi WebSocket User Data Stream tidak terputus."""
        while self.is_running:
            time.sleep(30 * 60)
            if self.listen_key:
                try:
                    client.futures_stream_keepalive(listenKey=self.listen_key)
                    logger.info("[WS KEEPALIVE] ListenKey Binance Futures berhasil diperbarui.")
                except Exception as e:
                    logger.error(f"[WS KEEPALIVE ERROR] Gagal memperbarui listenKey: {e}")

    def start(self):
        """Memulai koneksi WebSocket User Data Stream."""
        try:
            logger.info("Mendapatkan ListenKey User Data Stream Binance...")
            res = client.futures_stream_get_listen_key()
            self.listen_key = res if isinstance(res, str) else res.get("listenKey")
            
            if not self.listen_key:
                logger.error("Gagal memperoleh listenKey Binance WebSocket.")
                return
                
            logger.info(f"ListenKey didapatkan: {self.listen_key[:10]}... Menghubungkan ke WebSocket Binance...")
            
            self.bsm = BinanceSocketManager(client)
            self.is_running = True
            
            # Start Futures User Data Socket (python-binance v1.0.x API contract)
            if hasattr(self.bsm, 'futures_user_socket'):
                conn_key = self.bsm.futures_user_socket()
            elif hasattr(self.bsm, 'start_user_socket'):
                conn_key = self.bsm.start_user_socket(self.handle_user_data_message)
            else:
                conn_key = self.bsm.user_socket(self.handle_user_data_message)
                
            if hasattr(self.bsm, 'start'):
                self.bsm.start()
            elif hasattr(conn_key, 'start'):
                conn_key.start()
            
            self.keep_alive_thread = threading.Thread(target=self._keep_alive_listen_key, daemon=True)
            self.keep_alive_thread.start()
            
            logger.info("Binance User Data Stream WebSocket berhasil terhubung & mendengarkan event!")
        except Exception as e:
            logger.error(f"Gagal memulai Binance WebSocket Manager: {e}", exc_info=True)

    def stop(self):
        """Menghentikan koneksi WebSocket."""
        self.is_running = False
        if self.bsm:
            try:
                self.bsm.close()
                logger.info("Binance WebSocket Listener dihentikan.")
            except Exception as e:
                logger.error(f"Error saat menghentikan WebSocket: {e}")

# Shared global instance
ws_manager = BinanceWebSocketManager()
