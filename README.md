# gdlib

> CLI + TUI untuk mengunduh koleksi **Perpustakaan Universitas Gunadarma**
> (`library.gunadarma.ac.id`) — Repository (PI/Skripsi/Tesis/Disertasi),
> E-Paper, E-Book UG, Jurnal Ilmiah, dan pencarian Katalog OPAC.

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20TUI-blue)
![TUI](https://img.shields.io/badge/TUI-Textual-5A2D82)
![Status](https://img.shields.io/badge/status-aktif-success)

Memakai **akun kampus kamu sendiri**. Kredensial disimpan lokal di `.env`
(izin `600`, di-gitignore) dan hanya dikirim ke server Gunadarma.

## Fitur

- **Pencarian** lintas koleksi: Repository, E-Paper, E-Book, Jurnal, Katalog.
- **Filter repository** per jurusan (69 prodi), jenis penulisan, tahun, NPM,
  penulis, dan pembimbing.
- **Unduh PDF** satu per satu atau batch — tiap karya masuk subfolder sendiri
  (`<JUDUL> (<NPM>, <TAHUN>)/`).
- **Resumable batch** — proses yang terhenti bisa dilanjutkan tanpa mengulang.
- **TUI interaktif** (Textual) + **CLI** untuk skrip.

## Instalasi

Butuh Python 3.9+.

```bash
git clone https://github.com/azrahudaya/gdlib-gunadarma-library-downloader.git
cd gdlib-gunadarma-library-downloader
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Konfigurasi

```bash
cp .env.example .env
```

```ini
GDLIB_USERNAME=10123456789      # NPM / NIP
GDLIB_PASSWORD=passwordkamu
```

## Penggunaan

```bash
./gdlib.sh                                    # buka TUI

./gdlib.sh login                              # simpan sesi login
./gdlib.sh search repository "machine learning"
./gdlib.sh search repository "iot" --jurusan Informatika --jenis SKRIPSI --tahun 2024
./gdlib.sh download repository "jaringan" -n 3 -o ~/Downloads/gdlib

# Batch (resumable)
./.venv/bin/python scripts/batch_download.py --limit 50 \
    --jurusan 6 --jenis skripsi --tahun 2026 -o ~/Downloads/gdlib
```

**Pintasan TUI:** `F1` login · `F2` jurusan · `F5` cari · `F9` unduh item ·
`F10` unduh semua di halaman · `Ctrl+Q` keluar.

## Catatan

- **Jam Bebas Akses:** situs menutup akses publik pukul **23:00–03:00 WIB**
  (HTTP 503). Aplikasi menampilkan pesan yang jelas, bukan error.
- Sebagian berkas (LISTING PROGRAM, JURNAL WORD, dsb.) memang tidak
  dipublikasikan sehingga tidak bisa diunduh.
- Gunakan **hanya untuk keperluan akademik pribadi**. Hormati hak cipta dan
  ketentuan layanan perpustakaan; jangan menyebarkan ulang berkas.
- Struktur HTML situs dapat berubah; selektor di `gdlib/api.py` mungkin perlu
  disesuaikan.

## Lisensi

[MIT](LICENSE)
