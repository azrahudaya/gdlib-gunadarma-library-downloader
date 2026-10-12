# gdlib: Gunadarma Library Downloader

CLI and TUI tool to download collections from the **Universitas Gunadarma Library** (`library.gunadarma.ac.id`): repository (PI/Skripsi/Tesis/Disertasi), e-paper, e-book, journals, and OPAC catalog search.

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
![Interface](https://img.shields.io/badge/interface-CLI%20%2B%20TUI-blue)
![TUI](https://img.shields.io/badge/TUI-Textual-5A2D82)
![Status](https://img.shields.io/badge/status-active-success)

It uses **your own campus account**. Credentials are stored locally in `.env` (mode `600`, gitignored) and sent only to the Gunadarma server.

## Problem

Students who log in to the Gunadarma library often can only **read** documents in the browser. There is **no download button** on the reader page, so the PDFs cannot be saved or studied offline. Downloading one file at a time, by hand, is slow and painful.

This tool solves that:

- Downloads the actual PDF files that the web reader hides.
- Supports **batch download** of many works in one run, and can resume if interrupted.
- Saves every work into its own folder, so students can collect and study the PDFs offline.

## Features

- Search across collections: repository, e-paper, e-book, journal, catalog.
- Filter repository by major (69 programs), document type, year, NPM, author, and advisor.
- Download a single PDF or many at once, one folder per work (`<TITLE> (<NPM>, <YEAR>)/`).
- Resumable batch process: rerun the same command and it skips finished items.
- Interactive TUI (Textual) plus a CLI for scripting.

## Install

Requires Python 3.9+.

```bash
git clone https://github.com/azrahudaya/gdlib-gunadarma-library-downloader.git
cd gdlib-gunadarma-library-downloader
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Configuration

```bash
cp .env.example .env
```

```ini
GDLIB_USERNAME=10123456789      # NPM / NIP
GDLIB_PASSWORD=yourpassword
```

## Usage

```bash
./gdlib.sh                                    # open the TUI

./gdlib.sh login                              # save the login session
./gdlib.sh search repository "machine learning"
./gdlib.sh search repository "iot" --jurusan Informatika --jenis SKRIPSI --tahun 2024
./gdlib.sh download repository "network security" -n 3 -o ~/Downloads/gdlib

# Batch (resumable)
./.venv/bin/python scripts/batch_download.py --limit 50 \
    --jurusan 6 --jenis skripsi --tahun 2026 -o ~/Downloads/gdlib
```

**TUI shortcuts:** `F1` login, `F2` major, `F5` search, `F9` download selected, `F10` download page, `Ctrl+Q` quit.

## Notes

- **Free Access Hours:** the site blocks public access from **23:00 to 03:00 WIB** (HTTP 503). The app shows a clear message instead of an error.
- Some files (LISTING PROGRAM, JURNAL WORD, and similar) are not published, so they cannot be downloaded.
- Use this **for personal academic purposes only**. Respect copyright and the library terms of service. Do not redistribute the files.
- The site HTML can change at any time, so selectors in `gdlib/api.py` may need updates.

## Contributors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/azrahudaya">
        <img src="https://github.com/azrahudaya.png?size=120" width="120" alt="Azra Hudaya" /><br />
        <sub><b>Azra Hudaya</b></sub>
      </a>
    </td>
  </tr>
</table>

## License

[MIT](LICENSE)
