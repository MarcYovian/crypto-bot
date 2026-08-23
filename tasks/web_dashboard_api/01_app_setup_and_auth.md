# Task 01: FastAPI Application Setup & JWT Authentication

## 1. Deskripsi Task
Mempersiapkan fondasi aplikasi FastAPI, konfigurasi CORS middleware, utilitas keamanan password hashing & JWT token (Access Token + Refresh Token), dependency injection database session & autentikasi, serta mengimplementasikan modul autentikasi admin (`/api/v1/auth`).

---

## 2. File yang Akan Ditambah / Dimodifikasi

### File Baru:
* `backend/src/utils/security.py`: Utilitas hashing password (bcrypt/argon2) dan enkripsi/dekripsi JWT token dengan masa berlaku terkonfigurasi.
* `backend/src/api/__init__.py`: Inisialisasi package API.
* `backend/src/api/deps.py`: Dependency injection FastAPI (`get_db_session`, `get_current_user`, `require_admin_role`).
* `backend/src/api/routers/__init__.py`: Inisialisasi router.
* `backend/src/api/routers/auth.py`: Endpoint `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/me`.
* `backend/src/api/app.py`: Factory FastAPI application (`create_app()`), CORS middleware, global exception handlers, dan mounting router.
* `backend/tests/api/test_auth_api.py`: Test suite untuk auth router.

### File Dimodifikasi:
* `backend/config/settings.py`: Menambahkan variabel konfigurasi `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, dan `ADMIN_PASSWORD_HASH`.
* `requirements.txt`: Menambahkan `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `pyjwt>=2.8.0`, `passlib[bcrypt]>=1.7.4`.

---

## 3. Rincian Endpoint yang Diimplementasikan
* `POST /api/v1/auth/login`:
  * **Payload**: `LoginRequest` (`username`, `password`).
  * **Response (200)**: `LoginResponse` (`access_token`, `token_type: bearer`, `user: UserDTO`).
  * **Response (401)**: `ErrorResponse` jika kredensial salah.
* `POST /api/v1/auth/refresh`:
  * **Payload**: `{"refresh_token": "..."}`.
  * **Response (200)**: `{"access_token": "...", "token_type": "bearer"}`.
  * **Response (401)**: Jika refresh token expired / invalid.
* `GET /api/v1/auth/me`:
  * **Header**: `Authorization: Bearer <TOKEN>`.
  * **Response (200)**: `UserDTO` (`id`, `username`, `role: ADMIN`).

---

## 4. Kriteria Keberhasilan (Acceptance Criteria)
1. **Login Sukses**: Request ke `/api/v1/auth/login` dengan username/password yang valid mengembalikan JWT Access Token dan Refresh Token.
2. **Penolakan Kredensial Salah**: Request login dengan password salah mengembalikan HTTP status `401 Unauthorized`.
3. **Proteksi Route**: Request ke endpoint terproteksi (`/api/v1/auth/me`) tanpa token atau dengan token tidak valid ditolak dengan HTTP status `401 Unauthorized`.
4. **Token Refresh**: Refresh token yang valid berhasil menerbitkan access token baru.
5. **Testing**: Seluruh test di `backend/tests/api/test_auth_api.py` lulus 100% dan `mypy` tidak mendeteksi error.
