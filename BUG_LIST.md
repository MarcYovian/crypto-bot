Berikut adalah daftar seluruh error dan kendala teknis yang pernah Anda sampaikan beserta ringkasan penyebab dan titik perbaikannya agar memudahkan Anda saat *refactoring*:

---

### 1. `BinanceAPIException: APIError(code=-4509): Time in Force (TIF) GTE can only be used with open positions`

* **Penyebab:** Perintah *Stop Loss* (`STOP_MARKET`) dengan parameter `closePosition=True` dikirim saat posisi utama di Binance belum aktif/terisi (kuantitas masih `0`).
* **Titik Perbaikan:** Tambahkan jeda kecil (`time.sleep(1)`) dan validasi via `futures_position_information()` untuk memastikan posisi sudah resmi *Open* sebelum perintah SL dieksekusi.

---

### 2. `BinanceAPIException: APIError(code=-4005): Quantity greater than max quantity`

* **Penyebab:** Kuantitas order (`qty`) hasil kalkulasi *risk management* melampaui batas maksimal (`maxQty`) dari Binance (biasanya dipicu oleh jarak SL yang sangat tipis pada koin *altcoin/meme*).
* **Titik Perbaikan:** Ambil batas `maxQty` dari filter `LOT_SIZE` di `futures_exchange_info()`, lalu lakukan *capping* (batasi nilai `qty = min(calculated_qty, max_qty)`).

---

### 3. `APIError(code=-4067): Position side cannot be changed if there exists open orders`

* **Penyebab:** Bot mencoba mengubah *Position Mode* (misal ke *One-Way Mode*) sementara masih ada order gantung aktif pada koin lain di akun Binance.
* **Titik Perbaikan:** Atur *Position Mode* secara manual sekali saja via aplikasi/web Binance ke *One-Way Mode*, lalu **hapus** panggilan `futures_change_position_side()` dari kode bot (atau bungkus dengan `try-except` untuk mengabaikan error code `-4067`).

---

### 4. `HTTPSConnectionPool / TimeoutError: Read timed out. (read timeout=10)`

* **Penyebab:** Latensi/ketidakstabilan jaringan pada server VPS yang memicu *timeout* saat dipanggil oleh `infinity_polling` Telegram maupun API Binance Testnet.
* **Titik Perbaikan:**
* Naikkan timeout pada Telegram Bot: `bot.infinity_polling(timeout=60, long_polling_timeout=30)`.
* Tambahkan `requests_params={'timeout': 30}` saat inisialisasi `Client` Binance.
* Pastikan pada `docker-compose.yml` sudah terpasang `restart: always`.



---

### 5. `APIError(code=-1003): Way too many requests / IP banned`

* **Penyebab:** *Rate limit* Binance jebol akibat strategi REST API *polling* berulang di fungsi Cron saat memantau banyak koin aktif sekaligus.
* **Titik Perbaikan:**
* **Solusi Jangka Panjang:** Ubah sistem *monitoring* dari REST Polling ke **WebSocket Streaming** (`BinanceSocketManager`).
* **Solusi Cepat (REST):** Jangan panggil info posisi per-koin di dalam loop `for`. Panggil `client.futures_position_information()` **satu kali saja di luar loop** untuk mengambil seluruh data posisi secara masal.