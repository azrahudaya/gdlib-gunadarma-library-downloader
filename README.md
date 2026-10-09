# gdlib-dl

CLI + TUI (Python) untuk **mengunduh koleksi Perpustakaan Universitas Gunadarma**
(`https://library.gunadarma.ac.id`): Repository (PI/Skripsi/Tesis/Disertasi),
E-Paper, E-Book UG, Jurnal Ilmiah, dan pencarian Katalog OPAC.

> Alat ini memakai **akun kamu sendiri**. Kredensial disimpan lokal di `.env`
> (izin 600, di-gitignore) dan hanya dikirim ke server Gunadarma.

---

## 1. Apa yang sudah diverifikasi langsung ke situs

| Koleksi | Jumlah | Bisa diunduh? | Catatan |
|---|---|---|---|
| Repository (PI/Skripsi/Tesis/Disertasi) | ~295.000 | ✅ PDF multi-berkas | Lengkap **setelah login** |
| E-Paper (karya ilmiah + reader) | ~14.700 | ✅ PDF per-berkas | **Perlu login** |
| E-Book UG | ~1.600 | ✅ PDF | **Perlu login** |
| Jurnal Ilmiah | ~21.000 | ⚠️ umumnya hanya abstrak | PDF hanya jika tersedia |
| Katalog OPAC | ribuan | ❌ metadata saja | Buku tercetak |

**Detail teknis penting:**

- Login: Laravel. `GET /login` → ambil `_token` + cookie sesi → `POST /login`
  dengan `nomor_anggota` (NPM/NIP) + `password`. **Tanpa captcha.**
  Bisa pakai akun Perpustakaan **atau** Studentsite.
- Pencarian memakai fragmen HTML; header `X-Requested-With: XMLHttpRequest`
  mengembalikan blok hasil yang bersih.
- **Repository — dua jenis berkas:**
  - *Akses Terbuka* → tautan langsung `/repository/file/<id>?token=...`,
    bisa diunduh **tanpa login**, tapi hanya dari **sesi HTTP yang sama** dengan
    yang membuka halaman detail (endpoint menolak 403 jika sesi berbeda).
  - *Akses Kampus* (mis. BAB I–V) → tautan menuju **reader E-Paper**
    `/epaper/<key>`. PDF aslinya diambil dari `/epaper/fid/<fid>`, di mana `fid`
    ada di halaman reader sebagai `data-id` tiap `button.toc-btn`.
    **Wajib login** (bukan sekadar jaringan kampus). Saat belum login, href-nya
    tampil sebagai `/login?return_url=...` — program otomatis login lalu ambil ulang.
- E-Book: halaman `/ebooks/<slug>/baca` menyediakan
  `<div id="readSessionMeta" data-pdf-url="...">` → PDF e-book (perlu login).
- E-Paper: koleksi karya ilmiah yang sama, dengan reader bawaan (perlu login).
- **Filter `jurusan`:** server hanya menerima **satu** id prodi (nilai berkoma
  hanya memakai nilai pertama), dan value `fak_*` (semua fakultas) tidak
  berfungsi di endpoint GET. Karena itu filter jurusan disediakan per prodi
  (69 prodi) yang dikelompokkan per fakultas, bukan per fakultas.

---

## 2. Instalasi

Butuh Python 3.9+.

```bash
cd ~/gdlib-dl
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## 3. Konfigurasi kredensial

Salin contoh lalu isi dengan akun kamu:

```bash
cp .env.example .env
nano .env
```

```ini
GDLIB_USERNAME=10123456789      # NPM / NIP
GDLIB_PASSWORD=passwordkamu
```

`.env` sudah masuk `.gitignore` sehingga tidak ikut ter-commit.

## 4. Menjalankan

### Cara tercepat: perintah pintas

```bash
librarygunadarma
```

Perintah ini terpasang di `~/.local/bin/librarygunadarma` (sudah ada di PATH),
jadi dari terminal mana pun langsung membuka TUI. Argumen apa pun diteruskan,
misalnya `librarygunadarma search repository iot`.

### Lewat launcher proyek

Gunakan launcher `./gdlib.sh` (otomatis memakai venv proyek):

```bash
./gdlib.sh                       # buka TUI (tanpa argumen)
./gdlib.sh --help
```

### CLI

```bash
# Verifikasi & simpan sesi login
./gdlib.sh login
./gdlib.sh login --logout        # hapus sesi tersimpan

# Cari koleksi
./gdlib.sh search repository "machine learning"
./gdlib.sh search epaper "sistem informasi"      # perlu login
./gdlib.sh search ebooks "statistika"
./gdlib.sh search journal "voting"
./gdlib.sh search catalog "jaringan"

# Filter pencarian repository (nama boleh sebagian, lihat `gdlib filters`)
./gdlib.sh filters                               # daftar semua jurusan & jenis
./gdlib.sh search repository "iot" --jurusan "Informatika" --jenis SKRIPSI --tahun 2024
./gdlib.sh search repository "" --jurusan if     # alias: if=Informatika, si, sk, mi…
./gdlib.sh search repository "" --npm 50422108   # cari by NPM
./gdlib.sh search repository "" --penulis onno   # cari by nama penulis
./gdlib.sh search repository "" --pembimbing ravi

# Unduh hasil pencarian (N item pertama) — tiap karya masuk subfolder sendiri
./gdlib.sh download repository "klasifikasi serangan jaringan" -n 3 -o ~/Downloads/gdlib
./gdlib.sh download epaper "sistem informasi" -n 1 -o ~/Downloads/gdlib   # perlu login
./gdlib.sh download ebooks "ekonomi" -n 5          # perlu login

# Struktur hasil: <folder-induk>/<JUDUL (NPM, TAHUN)>/<berkas…>
# contoh: ~/Downloads/gdlib/PENERAPAN METODE … (50422108, 2026)/01_COVER_PENULISAN.pdf

# Unduh dari URL / slug tertentu (boleh berkali-kali)
./gdlib.sh download --url "https://library.gunadarma.ac.id/repository/<slug>"
./gdlib.sh download --url "<slug-skripsi>" --url "https://library.gunadarma.ac.id/ebooks/<slug>"

# Simpan laporan hasil unduhan
./gdlib.sh download repository "jaringan" -n 2 --report laporan.json
```

### TUI

```bash
./gdlib.sh
```

Baris atas: pilih koleksi (Repository / E-Paper / E-Book / Jurnal / Katalog) +
kotak kata kunci + tombol Cari. Baris kedua: **filter** (Repository) — tombol
**Fakultas/Jurusan**, dropdown jenis penulisan, kolom tahun, tombol **Filter
lain** (NPM/penulis/pembimbing) dan **Reset**. Baris chip menampilkan filter
yang sedang aktif. Kiri bawah: navigasi halaman (F6/F7).

**Filter jurusan paling gampang:** tekan **F2** (atau tombol
"Fakultas/Jurusan…") → muncul picker. Ketik mis. `info` → pilih
**Informatika (S1)**, Enter. Pencarian langsung dijalankan ulang dengan filter
itu. Daftar dikelompokkan per fakultas dan bisa dicari lewat nama atau alias
(`if` = Informatika, `si` = Sistem Informasi, `mi` = Manajemen Informatika…).

Pintasan:

| Tombol | Fungsi |
|---|---|
| `/` | Fokus ke kolom pencarian |
| `F2` | Pilih jurusan/fakultas (picker yang bisa dicari) |
| `F3` | Filter lanjutan (NPM / penulis / pembimbing) |
| `F4` | Reset semua filter |
| `F5` / Enter | Cari (mulai dari halaman 1) |
| `F6` / `F7` | Halaman sebelumnya / berikutnya |
| `F1` | Login (pakai kredensial `.env`) |
| `F9` | Unduh item yang disorot |
| `F10` | Unduh semua hasil di halaman ini |
| `Ctrl+Q` | Keluar |

Panel kanan menampilkan metadata + daftar berkas; panel bawah menampilkan
progress dan log unduhan. **Setiap karya diunduh ke subfoldernya sendiri** di
dalam folder induk (`~/Downloads/gdlib/`), dinamai `<JUDUL> (<NPM>, <TAHUN>)`,
jadi tiap skripsi rapi terpisah.

---

## 5. Struktur proyek

```
gdlib-dl/
├── gdlib/
│   ├── api.py        # klien HTTP: login, search, detail, download
│   ├── cli.py        # antarmuka CLI (argparse + rich)
│   ├── tui.py        # antarmuka TUI (textual)
│   └── __main__.py   # python -m gdlib
├── .env.example
├── requirements.txt
├── pyproject.toml
└── gdlib.sh          # launcher
```

## 6. Catatan & batasan

- **Jam Bebas Akses (penting):** Perpustakaan memblokir akses publik setiap
  **23:00–03:00 WIB** (halaman "Jam Bebas Akses", HTTP 503). Di luar jam itu
  login/pencarian/unduh normal kembali. Aplikasi menampilkan pesan jelas bila
  situs sedang tutup (bukan error).
- Unduh **hanya untuk keperluan akademik pribadi**. Hormati hak cipta dan
  ketentuan layanan perpustakaan; jangan menyebarkan ulang berkas.
- Sebagian berkas repository tidak dipublikasikan (mis. LISTING PROGRAM,
  JURNAL WORD, DOKUMEN PRESENTASI) sehingga tidak tersedia untuk diunduh.
- Struktur HTML situs bisa berubah sewaktu-waktu; bila pencarian/unduh berhenti
  bekerja, selektor di `gdlib/api.py` mungkin perlu disesuaikan.
- Sistem kedua `gunadarma.perpustakaan.co.id` (Kubuku/Digido) **tidak** ditangani
  karena memakai captcha dan engine berbeda.
