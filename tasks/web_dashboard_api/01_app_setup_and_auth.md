# Task 01: Database User Table, JWT Auth, In-Memory Cache & FastAPI Setup

## 1. Deskripsi Task
Mempersiapkan fondasi arsitektur Web Dashboard API:
1. Membuat tabel database **`users`** via Alembic migration (`id`, `username`, `password_hash`, `role`, `is_active`, `created_at`, `updated_at`) beserta `UserRepository` dan auto-seed user default `admin`.
2. Membangun modul keamanan password hashing (`bcrypt`) dan penerbitan JWT Access & Refresh Token (`src/utils/security.py`).
3. Membangun **In-Memory Asynchronous Cache Layer (`AsyncInMemoryCache`)** dengan fitur TTL dan smart key invalidation (`src/utils/cache.py`).
4. Membangun fondasi FastAPI (`src/api/app.py`), CORS middleware, dependency injection otorisasi (`src/api/deps.py`), dan router autentikasi (`/api/v1/auth`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/database/models/users.py`: Model SQLAlchemy tabel `users` (kolom: `id`, `username`, `password_hash`, `role`, `is_active`, `created_at`, `updated_at`).
* `backend/src/database/migration/versions/2026_08_23_2300-3a4b5c6d7e8f_create_users_table.py`: Migrasi Alembic untuk pembuatan tabel `users` dan indeks unique username.
* `backend/src/repository/user_repository.py`: `UserRepository` dengan method `get_by_username()`, `get_by_id()`, `create()`, `update_password()`, dan `ensure_default_admin()`.
* `backend/src/schemas/user.py`: Pydantic DTO `UserDTO`, `LoginRequest`, `LoginResponse`, `TokenRefreshRequest`.
* `backend/src/utils/security.py`: Utilitas hashing password (`bcrypt`) dan pembuatan/verifikasi JWT access & refresh token.
* `backend/src/utils/cache.py`: Utilitas caching in-memory asinkronus (`AsyncInMemoryCache`) dengan dukungan TTL dan pattern key invalidation.
* `backend/src/api/__init__.py`: Inisialisasi package API.
* `backend/src/api/deps.py`: Dependency injection FastAPI (`get_db_session`, `get_current_user`, `require_admin_role`, `get_cache`, `get_user_repo`).
* `backend/src/api/routers/__init__.py`: Inisialisasi router.
* `backend/src/api/routers/auth.py`: Endpoint `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/me`.
* `backend/src/api/app.py`: Factory FastAPI application (`create_app()`), CORS middleware, global exception handlers, dan mounting router.
* `backend/tests/repository/test_user_repository.py`: Test suite untuk `UserRepository` & auto-seed default admin.
* `backend/tests/api/test_auth_api.py`: Test suite untuk endpoint autentikasi & route protection.
* `backend/tests/test_cache_utility.py`: Test suite untuk utilitas caching (TTL expiration, key invalidation).

### File Dimodifikasi:
* `backend/src/database/models/__init__.py`: Export model `User`.
* `backend/src/repository/__init__.py`: Export repository `UserRepository`.
* `backend/src/schemas/__init__.py`: Export schema `UserDTO`, `LoginRequest`, `LoginResponse`.
* `backend/config/settings.py`: Menambahkan variabel konfigurasi `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD`.
* `requirements.txt`: Menambahkan `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `pyjwt>=2.8.0`, `passlib[bcrypt]>=1.7.4`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `POST /api/v1/auth/login`:
  * **Payload**: `LoginRequest` (`username`, `password`).
  * **Logika**: Query user dari `UserRepository.get_by_username()`, verifikasi password hash via `bcrypt`, dan terbitkan Access Token (exp: 60m) + Refresh Token (exp: 7d).
  * **Response (200)**: `LoginResponse` (`access_token`, `token_type: bearer`, `user: UserDTO`).
  * **Response (401)**: `ErrorResponse` jika username tidak ditemukan, password salah, atau akun non-aktif (`is_active = False`).
* `POST /api/v1/auth/refresh`:
  * **Payload**: `TokenRefreshRequest` (`refresh_token`).
  * **Logika**: Dekripsi dan validasi refresh token, terbitkan access token baru.
  * **Response (200)**: `{"access_token": "...", "token_type": "bearer"}`.
  * **Response (401)**: Jika refresh token expired / invalid.
* `GET /api/v1/auth/me`:
  * **Header**: `Authorization: Bearer <TOKEN>`.
  * **Logika**: Dependency `get_current_user` membaca `sub` dari JWT token dan mengambil data user dari database.
  * **Response (200)**: `UserDTO` (`id`, `username`, `role: ADMIN`, `is_active: true`).

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Tabel & Repository User**: Model `User` dan `UserRepository` berfungsi sempurna; method `ensure_default_admin()` otomatis membuat user default `admin` jika database baru diinisialisasi.
2. **Keamanan Password**: Password tersimpan dalam bentuk hash `bcrypt` (tidak pernah plaintext).
3. **Login Sukses**: Request ke `/api/v1/auth/login` dengan kredensial valid mengembalikan JWT Access Token dan Refresh Token.
4. **Penolakan Kredensial Salah**: Request login dengan username/password salah atau user nonaktif mengembalikan HTTP status `401 Unauthorized`.
5. **Proteksi Route**: Endpoint terproteksi (`/api/v1/auth/me`) menolak akses tanpa token valid (`401 Unauthorized`).
6. **In-Memory Cache**: `AsyncInMemoryCache` lulus pengujian TTL expiration dan key invalidation.
7. **Testing**: Seluruh test di `backend/tests/repository/test_user_repository.py`, `backend/tests/api/test_auth_api.py`, dan `backend/tests/test_cache_utility.py` lulus 100% dengan `mypy` 0 error.
