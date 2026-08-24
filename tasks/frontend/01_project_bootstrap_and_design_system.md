# Task 01: Project Bootstrap, TailwindCSS Design System & Atomic UI Components

## 1. Deskripsi Task
Menginisialisasi fondasi arsitektur proyek Frontend SPA (Vite + React 18 / Next.js 14 dengan TypeScript) dan membangun sistem desain visual "Cyber-Fintech Pro Terminal" berbasis TailwindCSS:
1. Inisialisasi konfigurasi proyek: `package.json`, `tsconfig.json`, `vite.config.ts` (atau `next.config.js`), dan plugin path aliases (`@/*`).
2. Konfigurasi `tailwind.config.js` dengan palet warna *Pro-Trading Dark Palette* (`--bg-canvas #080B10`, `--bg-surface #0F172A`, `--bg-card #1E293B`, `--border-default #334155`, aksen profit `#10B981`, loss `#EF4444`, warning `#F59E0B`, brand `#38BDF8`), tipografi (`Inter` & `JetBrains Mono`), dan efek glow / glassmorphism.
3. Menyiapkan file styling global `index.css` dengan CSS custom properties, utility classes untuk backdrop blur, custom dark scrollbar, dan animasi micro-pulse.
4. Membangun pustaka komponen UI atomik (*Radix UI / Shadcn UI primitives*): `Button`, `Input`, `Card`, `Badge`, `Modal/Dialog`, `Tooltip`, `Switch/Toggle`, `DropdownMenu`, `Tabs`, `Skeleton`, dan `Table`.
5. Membangun utilitas formatting numerik & finansial presisi (`src/utils/format.ts`) untuk mata uang USDT, persentase PnL, tanggal ISO 8601, durasi, dan konversi angka presisi tinggi tanpa bug floating-point.

---

## 2. File yang Akan Dibuat / Dimodifikasi

### File Konfigurasi, Base & Containerization:
* `frontend/package.json`: Definisi dependencies (`react`, `react-dom`, `@tanstack/react-query`, `zustand`, `axios`, `lucide-react`, `@radix-ui/*`, `clsx`, `tailwind-merge`, `tailwindcss-animate`, `lightweight-charts`).
* `frontend/tsconfig.json`: Konfigurasi TypeScript strict mode dengan path alias `@/*` -> `src/*`.
* `frontend/vite.config.ts`: Konfigurasi Vite dengan React plugin, proxy API ke `http://localhost:8000`, dan resolve alias.
* `frontend/tailwind.config.js`: Setup tema warna gelap, font sans/mono, custom box shadow glow, dan animation keyframes.
* `frontend/postcss.config.js`: Konfigurasi TailwindCSS dan Autoprefixer.
* `frontend/src/index.css`: Layer base, components, utilities, styling font `@font-face` / Google Fonts import (`Inter`, `JetBrains Mono`).
* `frontend/Dockerfile`: Multi-stage containerization build (`node:20-alpine` untuk build static assets `dist/` -> `nginx:alpine` untuk production web server).
* `frontend/nginx.conf`: Konfigurasi Nginx SPA routing (`try_files $uri $uri/ /index.html;`) dan reverse proxy `/api/v1/` serta `/api/v1/ws` ke backend.
* `frontend/.dockerignore`: Pengecualian `node_modules/`, `dist/`, `.git/`, `.env.local`.

### Komponen UI Primitif (Headless & Accessible):
* `frontend/src/components/ui/button.tsx`: Komponen Button dengan varian `primary`, `danger`, `outline`, `ghost`, `secondary` beserta loading spinner state.
* `frontend/src/components/ui/card.tsx`: Komponen Card dengan efek glassmorphism (`bg-slate-900/80 backdrop-blur-md border border-slate-800 rounded-xl`).
* `frontend/src/components/ui/badge.tsx`: Komponen Badge untuk `BUY/LONG` (emerald), `SELL/SHORT` (rose), `ADMIN`/`VIEWER`, status order, dan milestone TP.
* `frontend/src/components/ui/input.tsx`: Komponen Input monospaced dengan prefix/suffix (misal: `USDT`, `%`, `$`).
* `frontend/src/components/ui/modal.tsx`: Komponen Modal Dialog berbasis `@radix-ui/react-dialog` dengan transisi spring elegan (scale 95% -> 100%).
* `frontend/src/components/ui/switch.tsx`: Komponen Toggle Switch berbasis `@radix-ui/react-switch`.
* `frontend/src/components/ui/tabs.tsx`: Komponen Tab navigasi berbasis `@radix-ui/react-tabs`.
* `frontend/src/components/ui/tooltip.tsx`: Komponen Tooltip berbasis `@radix-ui/react-tooltip`.
* `frontend/src/components/ui/skeleton.tsx`: Komponen Skeleton placeholder dengan animasi shimmer untuk zero Cumulative Layout Shift (CLS).
* `frontend/src/components/ui/table.tsx`: Komponen Table wrapper dengan sticky header dan format sel monospaced.

### Utilitas & Helpers:
* `frontend/src/utils/cn.ts`: Utilitas penggabung class name (`clsx` + `tailwind-merge`).
* `frontend/src/utils/format.ts`: Fungsi helper presisi numerik:
  * `formatUSDT(val: number | string, decimals?: number): string` -> `$10,450.50`
  * `formatCrypto(val: number | string, precision?: number): string` -> `0.045 BTC`
  * `formatPercent(val: number | string, includeSign?: boolean): string` -> `+2.45%`
  * `formatDateTime(isoString: string): string` -> `2026-08-24 14:30:15`
  * `formatDuration(seconds: number): string` -> `2h 15m 30s`
* `frontend/src/types/common.ts`: Definisi type umum (PaginationParams, ApiResponse, ThemeMode, Role).

### Unit Tests:
* `frontend/tests/utils/format.test.ts`: Pengujian unit fungsi formatting numerik, persentase, tanggal, dan handling edge case (NaN, null, undefined, division by zero).
* `frontend/tests/components/ui.test.tsx`: Pengujian render komponen button, badge varian warna, dan modal dialog.

---

## 3. Rincian Spesifikasi Desain & Komponen

### 3.1 Design Tokens (Tailwind Extension)
```javascript
colors: {
  canvas: "#080B10",
  surface: "#0F172A",
  card: {
    DEFAULT: "#1E293B",
    hover: "#334155",
  },
  border: {
    subdued: "#1E293B",
    DEFAULT: "#334155",
    highlight: "#475569",
  },
  brand: {
    50: "#F0F9FF",
    400: "#38BDF8",
    500: "#3B82F6",
    600: "#2563EB",
  },
  trading: {
    profit: "#10B981",
    "profit-neon": "#00E676",
    loss: "#EF4444",
    "loss-neon": "#FF5252",
    warning: "#F59E0B",
    neutral: "#94A3B8",
  }
}
```

### 3.2 Numerical Hierarchy & Font Enforcement
* Label / Teks Antarmuka: `font-sans` (`Inter`).
* Angka Finansial (Saldo, PnL, Harga Mark, Lot Size, Stop Distance): Wajib menggunakan `font-mono` (`JetBrains Mono`).

---

## 4. Edge Cases & Error Handling
1. **Pencegahan Error Floating-Point**: Seluruh helper di `format.ts` memvalidasi input non-number, menangani pembulatan desimal tanpa distorsi JavaScript IEEE 754.
2. **Fallback Nilai Kosong**: Jika data bernilai `null` atau `undefined`, helper menampilkan `"-"` atau `$0.00` alih-alih melempar exception `TypeError`.
3. **Accessibility (a11y)**: Seluruh komponen interaktif (Button, Switch, Modal) menyertakan `aria-label`, support navigasi `Tab`, dan focus visible ring (`focus-visible:ring-2 focus-visible:ring-sky-400`).

---

## 5. Kriteria Keberhasilan (Acceptance Criteria)
1. Proyek berhasil dibuild tanpa warning/error dengan `npm run build`.
2. Seluruh token warna gelap, tipografi monospaced, dan efek glassmorphism terdaftar pada autocomplete TailwindCSS.
3. Seluruh unit test di `frontend/tests/utils/format.test.ts` lulus 100%.
4. Komponen UI atomik dapat dirender secara terisolasi tanpa runtime bug dan mematuhi standar aksesibilitas WCAG 2.1 AA.
