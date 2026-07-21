from backend.db.connection import init_db
from backend.config import bot
from backend.bot.handlers.signal_handler import register_handlers
from backend.services.binance_ws import ws_manager
from backend.logger import logger
from backend.jobs.scheduler import (
    cron_check_pending_orders,
    cron_monitor_active_positions,
    cron_sync_closed_positions,
    cron_cancel_expired_orders,
    cron_send_daily_report,
    cron_db_housekeeping,
    cron_check_api_health,
    cron_check_margin_level
)
from apscheduler.schedulers.background import BackgroundScheduler

if __name__ == "__main__":
    logger.info("Mempersiapkan Database...")
    init_db()
    
    logger.info("Menyiapkan Telegram Handlers...")
    register_handlers(bot)
    
    # Daftarkan daftar perintah agar muncul sebagai tombol/menu di Telegram
    from telebot import types
    try:
        bot.set_my_commands([
            types.BotCommand("status", "Melihat seluruh posisi aktif di Binance Futures"),
            types.BotCommand("summary", "Melihat rekapitulasi performa trading & Net PnL (PRD-V2)"),
            types.BotCommand("history", "Melihat 5 riwayat trade terakhir yang sudah ditutup"),
            types.BotCommand("close", "Menutup paksa posisi. (Contoh: /close BTCUSDT)"),
            types.BotCommand("cancel", "Membatalkan open orders koin. (Contoh: /cancel BTCUSDT)")
        ])
        logger.info("Menu Perintah Telegram berhasil didaftarkan.")
    except Exception as e:
        logger.warning(f"Gagal mendaftarkan menu perintah Telegram: {e}")
    
    logger.info("Memulai Binance WebSocket Stream Manager (Real-time Event Listener)...")
    try:
        ws_manager.start()
    except Exception as e:
        logger.error(f"Gagal memulai WebSocket Stream Manager: {e}")

    logger.info("Menyiapkan Cron Scheduler (Safety Net Fallback)...")
    scheduler = BackgroundScheduler()
    
    # 1. Cek limit order pending setiap 1 menit (karena real-time event sudah ditangani WebSocket)
    scheduler.add_job(cron_check_pending_orders, 'interval', minutes=1)
    
    # 2. Safety net fallback trailing SL & TP setiap 3 menit
    scheduler.add_job(cron_monitor_active_positions, 'interval', minutes=3)
    
    # 3. Sinkronisasi posisi tutup (bersih-bersih) setiap 1 menit
    scheduler.add_job(cron_sync_closed_positions, 'interval', minutes=1)
    
    # 4. Cek limit order pending yang kedaluwarsa (>4 jam) setiap 5 menit
    scheduler.add_job(cron_cancel_expired_orders, 'interval', minutes=5)
    
    # 5. Kirim laporan performa harian setiap hari pukul 23:59 WIB/UTC (sesuai jam sistem)
    scheduler.add_job(cron_send_daily_report, 'cron', hour=23, minute=59)
    
    # 6. Pembersihan database mingguan setiap hari Minggu pukul 00:00
    scheduler.add_job(cron_db_housekeeping, 'cron', day_of_week='sun', hour=0, minute=0)
    
    # 7. Memeriksa status kesehatan koneksi API Key setiap 30 menit
    scheduler.add_job(cron_check_api_health, 'interval', minutes=30)
    
    # 8. Memeriksa tingkat ketersediaan free margin setiap 10 menit
    scheduler.add_job(cron_check_margin_level, 'interval', minutes=10)
    
    scheduler.start()
    
    logger.info("Bot Telegram berjalan. Menunggu sinyal & WebSocket events...")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except (KeyboardInterrupt, SystemExit):
        ws_manager.stop()
        scheduler.shutdown()
        logger.info("Bot dihentikan.")
