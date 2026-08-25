# Task 02: Resilient Network Layer, JWT Authentication & Session State Management

## 1. Deskripsi Task
Membangun fondasi komunikasi HTTP, otentikasi pengguna berbasis JWT, manajemen sesi terisolasi di memory, mekanisme *silent token refresh* otomatis, dan sistem proteksi rute berbasis peran (RBAC):
1. Mengonfigurasi instance **Axios Client** (`src/api/client.ts`) dengan base URL, timeout, header interceptors, dan penanganan error standar.
2. Membangun **Axios Response Interceptor dengan Promise Queue Lock**: Saat request menerima respon `HTTP 401 Unauthorized` akibat access token kedaluwarsa ($15\text{ menit}$), interceptor secara transparan memanggil `POST /api/v1/auth/refresh`, menyimpan token baru ke memory, dan me-replay semua request yang sempat tertahan tanpa memutus alur kerja user.
3. Membangun **Zustand Auth Store (`useAuthStore`)**: Menyimpan access token di runtime memory, mengelola user profile (`UserDTO`), status login, role (`ADMIN` / `VIEWER`), serta aksi `login()`, `logout()`, `refreshSession()`, dan `checkAuth()`.
4. Membangun halaman **Login View (`src/features/auth/LoginPage.tsx`)** dengan validasi form, animasi loading, toggle password visibility, dan visual error feedback.
5. Membangun komponen penjaga rute **`AuthGuard`** dan pembatas akses **`RoleGuard`** yang melindungi rute sensitif (seperti `/settings` dan aksi mutasi).
6. Membangun komponen **`UserMenuBadge`** pada navbar atas yang menampilkan username, pill badge role, dan dropdown opsi *Logout*.

---

## 2. File yang Akan Dibuat / Dimodifikasi

### File API & Network:
* `frontend/src/api/client.ts`: Axios client singleton dengan request/response interceptors dan refresh queue lock logic.
* `frontend/src/api/endpoints/auth.ts`: Definisi fungsi API auth (`loginApi`, `refreshApi`, `getMeApi`).
* `frontend/src/types/auth.ts`: TypeScript interfaces (`LoginRequestDTO`, `LoginResponseDTO`, `UserDTO`, `TokenRefreshRequestDTO`).

### State & Stores:
* `frontend/src/stores/authStore.ts`: Zustand store untuk otentikasi, penyimpanan token di memory, dan persistensi refresh token di secure cookie/storage.

### Komponen & Halaman Auth:
* `frontend/src/features/auth/LoginPage.tsx`: Halaman login pro-terminal dengan kartu glassmorphism, input username/password, tombol submit, dan alert notifikasi.
* `frontend/src/features/auth/AuthGuard.tsx`: Wrapper rute yang memvalidasi sesi aktif sebelum merender halaman protected.
* `frontend/src/features/auth/RoleGuard.tsx`: Komponen kondisional yang menyembunyikan atau menonaktifkan tombol mutasi jika role adalah `VIEWER`.
* `frontend/src/features/auth/UserMenuBadge.tsx`: Badge profil user di top navbar dengan indikator role (`ADMIN` gold/purple, `VIEWER` slate) dan action logout.

### Unit & Integration Tests:
* `frontend/tests/api/auth_interceptor.test.ts`: Pengujian interceptor silent token refresh (termasuk skenario concurrent requests saat token expired).
* `frontend/tests/stores/auth_store.test.ts`: Pengujian state transitions `useAuthStore` (login, logout, session expiration).
* `frontend/tests/features/login_page.test.tsx`: Pengujian form validation, error message rendering, dan redirect setelah login sukses.

---

## 3. Rincian Endpoint API yang Diintegrasikan

### 1. `POST /api/v1/auth/login`
* **Request Body**: `LoginRequest` (`username: string`, `password: string`).
* **Response (200 OK)**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "user": {
      "id": 1,
      "username": "admin",
      "role": "ADMIN"
    }
  }
  ```
* **Response (401 Unauthorized)**: `ErrorResponse` (`detail: "Invalid credentials"`).

### 2. `POST /api/v1/auth/refresh`
* **Request Body**: `{"refresh_token": "eyJhbGciOi..."}`.
* **Response (200 OK)**: `{"access_token": "eyJhbGciOi...", "token_type": "bearer"}`.
* **Response (401 Unauthorized)**: Refresh token kedaluwarsa atau di-blacklist.

### 3. `GET /api/v1/auth/me`
* **Header**: `Authorization: Bearer <access_token>`.
* **Response (200 OK)**: `UserDTO` (`id`, `username`, `role`).

---

## 4. Rincian Alur Logika & Interaktivitas

### 4.1 Mekanisme Silent Token Refresh (Promise Queue Lock)
```typescript
let isRefreshing = false;
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: any) => void }> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) prom.reject(error);
    else prom.resolve(token!);
  });
  failedQueue = [];
};
```
* Saat request pertama kali mendapat 401 dan `!isRefreshing`: set `isRefreshing = true`, panggil `refreshApi()`.
* Request lain yang datang bersamaan dimasukkan ke dalam `failedQueue`.
* Setelah refresh sukses: update access token di memory, jalankan semua callback di `failedQueue` dengan token baru, dan replay request awal.
* Jika refresh gagal: bersihkan sesi, panggil `logout()`, dan redirect ke `/login`.

### 4.2 Role-Based Access Control (RBAC) Guard
* `RoleGuard` mengecek `user.role === 'ADMIN'`. Jika user berstatus `VIEWER`, tombol mutasi (seperti *Execute Signal*, *Panic Close*, *Pause Bot*, *Sync Instruments*) otomatis di-disable atau dirender dengan tooltip peringatan *"Hanya untuk Administrator"*.

---

## 5. Edge Cases & Error Handling
1. **Concurrent Request Race Condition**: Mekanisme queue lock menjamin endpoint `/api/v1/auth/refresh` hanya dipanggil **tepat 1 kali** meskipun ada 10 query yang fail bersamaan.
2. **Refresh Token Expired / Blacklisted**: Sesi dibersihkan total (`clearAuth`), user langsung diarahkan ke `/login` dengan toast: *"Sesi Anda telah berakhir. Silakan login kembali."*
3. **Form Brute-Force Feedback**: Tombol submit login otomatis dinonaktifkan dengan spinner saat request sedang berjalan untuk mencegah spam klik.
4. **Manipulasi Role di Client**: Setiap request API tetap divalidasi oleh backend FastAPI (`HTTP 403 Forbidden` jika non-admin mencoba eksekusi mutasi).

---

## 6. Kriteria Keberhasilan (Acceptance Criteria)
1. User dapat login dengan kredensial valid, diarahkan ke `/dashboard`, dan melihat nama serta badge role di navbar.
2. Login dengan kredensial salah menampilkan pesan error merah dan form tidak di-reset total.
3. Access token kedaluwarsa secara transparan diperbarui di latar belakang tanpa menyebabkan error di layar pengguna.
4. User dengan role `VIEWER` tidak dapat mengakses menu `/settings` dan tombol aksi trading terkunci.
5. Seluruh test di `frontend/tests/api/auth_interceptor.test.ts`, `frontend/tests/stores/auth_store.test.ts`, dan `frontend/tests/features/login_page.test.tsx` lulus 100%.
