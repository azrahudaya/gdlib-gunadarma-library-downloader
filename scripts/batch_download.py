"""Batch downloader untuk gdlib-dl: unduh N karya lengkap (semua berkas).

Resumable: tiap karya yang selesai dicatat di state file; dijalankan ulang akan
melewati yang sudah beres. Cocok dijalankan di background.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gdlib.cli import load_env  # noqa: E402
from gdlib.api import GunadarmaClient, AuthError, ClosedError, GdError  # noqa: E402


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_done() -> set:
    done = set()
    if os.path.exists(STATE_PATH):
        for line in open(STATE_PATH, encoding="utf-8"):
            try:
                rec = json.loads(line)
                if rec.get("files_ok", 0) > 0:
                    done.add(rec["url"])
            except Exception:
                pass
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--jurusan", default="6", help="6 = Informatika (S1)")
    ap.add_argument("--jenis", default="skripsi")
    ap.add_argument("--tahun", default="2026", help="> 2025")
    ap.add_argument("-o", "--out", default=os.path.expanduser("~/Downloads/gdlib"))
    ap.add_argument("--state", default="/tmp/gdlib_batch/state.jsonl")
    ap.add_argument("--log", default="/tmp/gdlib_batch/batch.log")
    args = ap.parse_args()

    global STATE_PATH, LOG_PATH
    STATE_PATH, LOG_PATH = args.state, args.log
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

    load_env(".env")
    c = GunadarmaClient(username=os.environ.get("GDLIB_USERNAME"),
                        password=os.environ.get("GDLIB_PASSWORD"))
    try:
        c.login()
    except GdError as e:
        log(f"LOGIN GAGAL: {e}")
        return 2
    log(f"login OK sebagai {c.username}")

    done = load_done()

    # --- kumpulkan item (banyak halaman bila perlu) ---
    items, seen, page = [], set(), 1
    while len(items) < args.limit and page <= 200:
        try:
            batch, total = c.search("repository", q="", page=page,
                                    filters={"jurusan": args.jurusan,
                                             "jenis": args.jenis,
                                             "tahun": args.tahun})
        except ClosedError as e:
            log(f"SITUS TUTUP: {e}")
            return 3
        if not batch:
            break
        for it in batch:
            if it.url not in seen:
                seen.add(it.url)
                items.append(it)
        log(f"  halaman {page}: +{len(batch)} (terkumpul {len(items)})")
        page += 1
    items = items[:args.limit]
    log(f"target: {len(items)} skripsi · sudah selesai sebelumnya: {len(done)}")

    ok_items = tot_files = 0
    t_start = time.time()
    for n, it in enumerate(items, 1):
        if it.url in done:
            log(f"[{n}/{len(items)}] SKIP (sudah beres)")
            ok_items += 1
            continue
        t0 = time.time()
        try:
            res = c.download_item(it.url, args.out, log=lambda m: log("     " + m))
        except ClosedError as e:
            log(f"[{n}/{len(items)}] SITUS TUTUP: {e}")
            break
        except GdError as e:
            log(f"[{n}/{len(items)}] GAGAL: {e}")
            continue
        n_ok = sum(1 for r in res if r.get("status") == "ok")
        folder = res[0].get("folder", "") if res else ""
        rec = {"url": it.url, "title": it.title, "npm": it.author,
               "folder": folder, "files_ok": n_ok, "files_total": len(res),
               "elapsed": round(time.time() - t0, 1)}
        with open(STATE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tot_files += n_ok
        if n_ok:
            ok_items += 1
        log(f"[{n}/{len(items)}] {'OK' if n_ok else 'KOSONG'} "
            f"{n_ok}/{len(res)} berkas · {os.path.basename(folder)[:45]} · "
            f"{rec['elapsed']}s")
        time.sleep(1.0)

    mins = (time.time() - t_start) / 60
    log(f"SELESAI: {ok_items}/{len(items)} skripsi · {tot_files} berkas · {mins:.1f} menit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
