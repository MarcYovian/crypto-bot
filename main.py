from database import init_db
from config import bot
from handlers import register_handlers
from scheduler import (
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
    print("Mempersiapkan Database...")
    init_db()
    
    print("Menyiapkan Telegram Handlers...")
    register_handlers(bot)
    
    # Daftarkan daftar perintah agar muncul sebagai tombol/menu di Telegram
    from telebot import types
    try:
        bot.set_my_commands([
            types.BotCommand("status", "Melihat seluruh posisi aktif di Binance Futures"),
            types.BotCommand("positions", "Melihat seluruh posisi aktif di Binance Futures"),
            types.BotCommand("close", "Menutup paksa posisi. (Contoh: /close BTCUSDT)"),
            types.BotCommand("cancel", "Membatalkan open orders koin. (Contoh: /cancel BTCUSDT)")
        ])
        print("Menu Perintah Telegram berhasil didaftarkan.")
    except Exception as e:
        print(f"[WARN] Gagal mendaftarkan menu perintah Telegram: {e}")
    
    print("Menyiapkan Cron Scheduler...")
    scheduler = BackgroundScheduler()
    
    # 1. Cek limit order pending setiap 30 detik
    scheduler.add_job(cron_check_pending_orders, 'interval', seconds=30)
    
    # 2. Cek pergerakan harga posisi aktif (trailing Stop Loss & status TP) setiap 1 menit
    scheduler.add_job(cron_monitor_active_positions, 'cron', minute='*')
    
    # 3. Sinkronisasi posisi tutup (bersih-bersih) setiap 15 detik
    scheduler.add_job(cron_sync_closed_positions, 'interval', seconds=15)
    
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
    
    print("Bot Telegram berjalan. Menunggu sinyal...")
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Bot dihentikan.")
