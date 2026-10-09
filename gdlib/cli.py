"""Command line interface for gdlib-dl."""
from __future__ import annotations

import argparse
import json
import os
import sys

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from . import __version__
from .api import (
    BASE,
    JENIS,
    JURUSAN,
    JURUSAN_GROUPS,
    KIND_LABEL,
    KINDS,
    AuthError,
    ClosedError,
    GdError,
    GunadarmaClient,
    normalize_url,
    resolve_jenis,
    resolve_jurusan,
)

console = Console()


def load_env(path: str = ".env") -> None:
    """Minimal .env loader (KEY=VALUE). Does not override real env vars."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


def make_client(args) -> GunadarmaClient:
    load_env(args.env)
    user = args.username or os.environ.get("GDLIB_USERNAME")
    pw = args.password or os.environ.get("GDLIB_PASSWORD")
    return GunadarmaClient(username=user, password=pw, session_file=args.session_file)


def parse_filters(args) -> dict:
    f: dict = {}
    if getattr(args, "jenis", None):
        f["jenis"] = resolve_jenis(args.jenis)
    if getattr(args, "jurusan", None):
        f["jurusan"] = resolve_jurusan(args.jurusan)
    if getattr(args, "tahun", None):
        f["tahun"] = args.tahun
    for key in ("npm", "penulis", "pembimbing", "nomor_induk"):
        v = getattr(args, key, None)
        if v:
            f[key] = v
    for kv in getattr(args, "filter", []) or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            f[k.strip()] = v.strip()
    return f


# --------------------------------------------------------------------- commands
def cmd_login(args) -> int:
    c = make_client(args)
    if args.logout:
        c.clear_session()
        console.print("[yellow]Sesi lokal dihapus.[/yellow]")
        return 0
    try:
        c.login()
    except ClosedError as e:
        console.print(f"[yellow]⚠ {e}[/yellow]")
        return 3
    except AuthError as e:
        console.print(f"[red]{e}[/red]")
        return 2
    ok = c.is_logged_in()
    console.print(f"[green]Login berhasil[/green] sebagai {c.username}" if ok
                  else "[yellow]Login terkirim tapi verifikasi gagal.[/yellow]")
    return 0 if ok else 1


def _print_items(items, total):
    t = Table(show_lines=False, header_style="bold cyan")
    t.add_column("#", justify="right", width=3)
    t.add_column("Jenis", width=10)
    t.add_column("Judul", overflow="fold")
    t.add_column("Penulis/NPM", width=22, overflow="fold")
    t.add_column("Tahun", width=6)
    t.add_column("Dilihat", width=9, justify="right")
    for i, it in enumerate(items, 1):
        t.add_row(str(i), it.tag or it.kind, it.title, it.author, it.year, it.views)
    console.print(t)
    console.print(
        f"[dim]{len(items)} item ditampilkan"
        + (f" dari total {total:,}" if total else "")
        + "[/dim]"
    )


def cmd_search(args) -> int:
    c = make_client(args)
    try:
        items, total = c.search(args.kind, q=args.query or "", page=args.page,
                                filters=parse_filters(args))
    except AuthError as e:
        console.print(f"[red]{e}[/red]")
        return 2
    except GdError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    if args.json:
        console.print_json(json.dumps(
            {"total": total, "items": [it.to_dict() for it in items]},
            ensure_ascii=False))
        return 0
    _print_items(items, total)
    if not args.no_urls:
        for i, it in enumerate(items, 1):
            console.print(f"[dim]{i:>3}. {it.url}[/dim]")
    return 0


def cmd_download(args) -> int:
    c = make_client(args)
    filters = parse_filters(args)
    out_dir = os.path.abspath(args.out)

    targets: list[str] = []
    if args.url:
        for u in args.url:
            targets.append(normalize_url(u, args.kind))
    else:
        if not args.query:
            console.print("[red]Butuh QUERY atau --url.[/red]")
            return 1
        try:
            n = args.limit
            for it in c.iter_search(args.kind, q=args.query, filters=filters,
                                    max_items=n):
                targets.append(it.url)
        except GdError as e:
            console.print(f"[red]{e}[/red]")
            return 1
        console.print(f"[cyan]{len(targets)} item akan diproses.[/cyan]")

    if not targets:
        console.print("[yellow]Tidak ada item.[/yellow]")
        return 1

    all_results = []
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(), DownloadColumn(), TransferSpeedColumn(),
        TimeRemainingColumn(), console=console, transient=False,
    )

    with progress:
        for url in targets:
            task = progress.add_task("menyiapkan…", total=None)

            def cb(label, done, total, task=task):
                progress.update(task, description=label[:40],
                                completed=done, total=total or None)

            try:
                res = c.download_item(url, out_dir, progress=cb,
                                      log=lambda m: progress.console.log(m))
            except GdError as e:
                progress.console.log(f"[red]{url}: {e}[/red]")
                res = [{"url": url, "status": "error", "error": str(e)}]
            all_results.extend(res)
            progress.update(task, description="selesai", total=1, completed=1)

    ok = sum(1 for r in all_results if r.get("status") == "ok")
    console.print(f"\n[green]Selesai[/green]: {ok} file diunduh ke {out_dir}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        console.print(f"[dim]Laporan: {args.report}[/dim]")
    return 0


def cmd_tui(args) -> int:
    from .tui import run_tui

    run_tui(args)
    return 0


def cmd_filters(args) -> int:
    if args.what in ("jurusan", "semua"):
        t = Table(title="Filter jurusan (repository) — 69 prodi",
                  header_style="bold cyan", show_lines=False)
        t.add_column("Grup / Fakultas", style="dim")
        t.add_column("Jurusan")
        t.add_column("Value", justify="right", style="green")
        for group, progs in JURUSAN_GROUPS.items():
            for name, jid in progs:
                t.add_row(group, name, jid)
        console.print(t)
        console.print("[dim]Pakai: --jurusan \"Informatika\" · --jurusan if "
                      "· --jurusan \"Sistem Informasi\" (nama boleh sebagian).[/dim]")
    if args.what in ("jenis", "semua"):
        t = Table(title="Filter jenis penulisan (repository)", header_style="bold cyan")
        t.add_column("Nama")
        t.add_column("Kode")
        for name, code in JENIS.items():
            if code:
                t.add_row(name, code)
        console.print(t)
        console.print("[dim]Pakai: --jenis SKRIPSI · --jenis tesis[/dim]")
    console.print("[dim]Filter lain: --tahun 2024 · --npm 50422108 · "
                  "--penulis nama · --pembimbing nama · --filter K=V[/dim]")
    return 0


# ------------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gdlib",
        description="Unduh koleksi Perpustakaan Universitas Gunadarma "
                    "(repository, e-book, jurnal) — library.gunadarma.ac.id",
    )
    p.add_argument("--version", action="version", version=f"gdlib-dl {__version__}")
    p.add_argument("--env", default=".env", help="lokasi file .env (default: .env)")
    p.add_argument("--username", help="nomor anggota / NPM (menimpa .env)")
    p.add_argument("--password", help="password (menimpa .env)")
    p.add_argument("--session-file", default=None, help="lokasi cache sesi")
    sub = p.add_subparsers(dest="cmd")

    # login
    sl = sub.add_parser("login", help="verifikasi & simpan sesi login")
    sl.add_argument("--logout", action="store_true", help="hapus sesi tersimpan")
    sl.set_defaults(func=cmd_login)

    # search
    ss = sub.add_parser("search", help="cari koleksi")
    ss.add_argument("kind", choices=KINDS, help="jenis koleksi")
    ss.add_argument("query", nargs="?", default="", help="kata kunci")
    ss.add_argument("--page", type=int, default=1)
    ss.add_argument("--jenis", help="filter jenis penulisan, mis. SKRIPSI (lihat `gdlib filters`)")
    ss.add_argument("--jurusan", help="filter jurusan/fakultas, mis. \"Informatika\" atau fasilkom")
    ss.add_argument("--tahun", help="filter tahun, mis. 2024")
    ss.add_argument("--npm", help="filter nomor pokok mahasiswa, mis. 50422108")
    ss.add_argument("--penulis", help="filter nama penulis")
    ss.add_argument("--pembimbing", help="filter nama pembimbing")
    ss.add_argument("--filter", action="append", metavar="K=V",
                    help="filter tambahan, mis. nomor_induk=123")
    ss.add_argument("--json", action="store_true", help="keluaran JSON")
    ss.add_argument("--no-urls", action="store_true", help="jangan cetak URL")
    ss.set_defaults(func=cmd_search)

    # download
    sd = sub.add_parser("download", help="unduh hasil pencarian / URL")
    sd.add_argument("kind", choices=KINDS, nargs="?", default="repository")
    sd.add_argument("query", nargs="?", default="", help="kata kunci pencarian")
    sd.add_argument("--url", action="append", help="URL atau slug item (boleh berkali-kali)")
    sd.add_argument("-n", "--limit", type=int, default=10,
                    help="maksimum item dari hasil pencarian (default 10)")
    sd.add_argument("-o", "--out", default=os.path.expanduser("~/Downloads/gdlib"),
                    help="folder induk tujuan (default: ~/Downloads/gdlib); "
                         "tiap karya dibuatkan subfolder sendiri")
    sd.add_argument("--jenis", help="filter jenis penulisan, mis. SKRIPSI")
    sd.add_argument("--jurusan", help="filter jurusan/fakultas, mis. \"Informatika\"")
    sd.add_argument("--tahun", help="filter tahun, mis. 2024")
    sd.add_argument("--npm", help="filter nomor pokok mahasiswa")
    sd.add_argument("--penulis", help="filter nama penulis")
    sd.add_argument("--pembimbing", help="filter nama pembimbing")
    sd.add_argument("--filter", action="append", metavar="K=V")
    sd.add_argument("--report", help="simpan laporan JSON ke file")
    sd.set_defaults(func=cmd_download)

    # filters
    sf = sub.add_parser("filters", help="tampilkan daftar jurusan / jenis penulisan")
    sf.add_argument("what", nargs="?", choices=("semua", "jurusan", "jenis"),
                    default="semua")
    sf.set_defaults(func=cmd_filters)

    # tui
    st = sub.add_parser("tui", help="antarmuka TUI (default bila tanpa perintah)")
    st.set_defaults(func=cmd_tui)

    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        args = p.parse_args((argv or sys.argv[1:]) + ["tui"])
    try:
        return args.func(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dibatalkan.[/yellow]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
