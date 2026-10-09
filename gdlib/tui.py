"""Textual TUI for gdlib-dl."""
from __future__ import annotations

import os

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    ProgressBar,
    RichLog,
    Select,
    Static,
)

from .api import (
    JENIS,
    JURUSAN,
    KIND_LABEL,
    KINDS,
    AuthError,
    ClosedError,
    GdError,
    GunadarmaClient,
    normalize_url,
)

KIND_CHOICES = [(KIND_LABEL[k], k) for k in KINDS]
JENIS_CHOICES = [(name, code) for name, code in JENIS.items()]
JURUSAN_CHOICES = [(name, jid) for name, jid in JURUSAN.items()]


class GdTui(App):
    CSS = """
    Screen { layout: vertical; }
    #searchbar { height: 3; dock: top; padding: 0 1; }
    #searchbar Select { width: 34; }
    #searchbar Input { width: 1fr; }
    #searchbar Button { width: 12; margin: 0 0 0 1; }
    #filterbar { height: 3; padding: 0 1; }
    #filterbar Label { width: auto; padding: 1 1 0 0; color: $text-muted; }
    #filterbar Select { width: 30; }
    #filterbar Input { width: 8; }
    #main { height: 1fr; }
    #left { width: 3fr; }
    #right { width: 2fr; border-left: solid $panel; padding: 0 1; }
    #results { height: 1fr; }
    #detail { padding: 1; }
    #bottom { height: 8; border-top: solid $panel; }
    #prog { height: 1; }
    #log { height: 1fr; }
    #status { dock: bottom; height: 1; padding: 0 1; color: $text-muted; }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Keluar"),
        ("f1", "login", "Login"),
        ("f5", "do_search", "Cari"),
        ("f9", "download_selected", "Unduh item"),
        ("f10", "download_all", "Unduh semua hasil"),
        ("/", "focus_search", "Cari…"),
    ]

    def __init__(self, args):
        super().__init__()
        self.args = args
        from .cli import load_env

        load_env(getattr(args, "env", ".env"))
        user = getattr(args, "username", None) or os.environ.get("GDLIB_USERNAME")
        pw = getattr(args, "password", None) or os.environ.get("GDLIB_PASSWORD")
        self.client = GunadarmaClient(
            username=user, password=pw,
            session_file=getattr(args, "session_file", None),
        )
        self.out_dir = os.path.abspath(getattr(args, "out", None) or "downloads")
        self.items = []
        self.current_kind = "repository"
        self._pending: list[str] = []
        if self.client.logged_in:
            self._pending.append(
                f"Sesi tersimpan ditemukan (user: {self.client.username or '?'}).")

    # ------------------------------------------------------------------- layout
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="searchbar"):
            yield Select(KIND_CHOICES, value="repository", id="kind")
            yield Input(placeholder="kata kunci… lalu Enter", id="query")
            yield Button("Cari", id="btn_search", variant="primary")
        with Horizontal(id="filterbar"):
            yield Static("Filter (Repository):")
            yield Select([("Semua jurusan", "")] + JURUSAN_CHOICES, value="", id="f_jurusan")
            yield Select([("Semua jenis", "")] + JENIS_CHOICES, value="", id="f_jenis")
            yield Input(placeholder="tahun", id="f_tahun")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield DataTable(id="results", zebra_stripes=True, cursor_type="row")
            with VerticalScroll(id="right"):
                yield Static("Pilih item untuk melihat detail.", id="detail")
        with Vertical(id="bottom"):
            yield ProgressBar(id="prog", show_eta=False)
            yield RichLog(id="log", markup=True, wrap=True, highlight=False)
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#results", DataTable)
        t.add_columns("#", "Jenis", "Judul", "Penulis", "Tahun")
        self._log("gdlib-dl TUI siap. F1 login · / cari · F9 unduh item · F10 unduh semua.")
        self._log("[dim]Tip: pilih koleksi di kiri. Filter jurusan/jenis aktif "
                  "untuk Repository. E-Paper & E-Book perlu login.[/dim]")
        for m in self._pending:
            self._log(m)
        self._pending.clear()
        self._set_status()

    # ------------------------------------------------------------------- helpers
    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def _set_status(self, extra: str = "") -> None:
        who = self.client.username or "(belum login)"
        st = "login ✓" if self.client.logged_in else "belum login"
        self.query_one("#status", Static).update(
            f"user: {who} · {st} · tujuan: {self.out_dir} {extra}"
        )

    def _kind(self) -> str:
        v = self.query_one("#kind", Select).value
        return v if isinstance(v, str) else "repository"

    def _active_filters(self) -> dict:
        f: dict = {}
        jur = self.query_one("#f_jurusan", Select).value
        jen = self.query_one("#f_jenis", Select).value
        thn = self.query_one("#f_tahun", Input).value.strip()
        if isinstance(jur, str) and jur:
            f["jurusan"] = jur
        if isinstance(jen, str) and jen:
            f["jenis"] = jen
        if thn:
            f["tahun"] = thn
        return f

    def _show_items(self, items, total) -> None:
        self.items = items
        t = self.query_one("#results", DataTable)
        t.clear()
        for i, it in enumerate(items, 1):
            t.add_row(str(i), it.tag or it.kind, it.title[:90],
                      it.author[:24], it.year, key=str(i - 1))
        extra = f"· {len(items)} hasil"
        if total:
            extra += f" dari {total:,}"
        self._set_status(extra)
        self._log(f"[cyan]{len(items)} item ditampilkan"
                  + (f" dari total {total:,}" if total else "") + "[/cyan]")
        if items:
            t.move_cursor(row=0)
            self._show_detail(items[0])

    def _show_detail(self, item) -> None:
        lines = [f"[bold]{item.title}[/bold]"]
        if item.author:
            lines.append(f"[dim]Penulis/NPM:[/dim] {item.author}")
        if item.year:
            lines.append(f"[dim]Tahun:[/dim] {item.year}")
        lines.append(f"[dim]Jenis:[/dim] {item.tag or item.kind}")
        lines.append(f"[dim]URL:[/dim] {item.url}")
        if item.abstract:
            lines.append("")
            lines.append(item.abstract[:600])
        if item.files:
            lines.append("")
            lines.append("[bold]Berkas:[/bold]")
            for i, f in enumerate(item.files, 1):
                lines.append(f"  {i:>2}. {f['label']}  [dim]({f['access']})[/dim]")
        self.query_one("#detail", Static).update("\n".join(lines))

    # ------------------------------------------------------------------- events
    @on(DataTable.RowHighlighted, "#results")
    def _row_hl(self, event: DataTable.RowHighlighted) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self.items):
            self._show_detail(self.items[idx])

    @on(Input.Submitted, "#query")
    def _submitted(self, event: Input.Submitted) -> None:
        self.action_do_search()

    @on(Input.Submitted, "#f_tahun")
    def _submitted_year(self, event: Input.Submitted) -> None:
        self.action_do_search()

    @on(Button.Pressed, "#btn_search")
    def _btn_search(self, event: Button.Pressed) -> None:
        self.action_do_search()

    def action_focus_search(self) -> None:
        self.query_one("#query", Input).focus()

    def action_do_search(self) -> None:
        q = self.query_one("#query", Input).value.strip()
        kind = self._kind()
        self.current_kind = kind
        filters = self._active_filters() if kind == "repository" else {}
        self._log(f"[yellow]Mencari[/yellow] '{q}' di {KIND_LABEL[kind]} "
                  + (f"· filter {filters}" if filters else "") + " …")
        self._search_worker(kind, q, filters)

    def action_login(self) -> None:
        if not self.client.username or not self.client.password:
            self._log("[red]Set GDLIB_USERNAME & GDLIB_PASSWORD di .env dulu.[/red]")
            return
        self._log("[yellow]Login…[/yellow]")
        self._login_worker()

    def action_download_selected(self) -> None:
        t = self.query_one("#results", DataTable)
        idx = t.cursor_row
        if not self.items or not (0 <= idx < len(self.items)):
            self._log("[red]Belum ada item terpilih.[/red]")
            return
        item = self.items[idx]
        self._log(f"[yellow]Mengunduh:[/yellow] {item.title[:60]}")
        self._download_worker([item.url])

    def action_download_all(self) -> None:
        if not self.items:
            self._log("[red]Belum ada hasil. Cari dulu.[/red]")
            return
        urls = [it.url for it in self.items]
        self._log(f"[yellow]Mengunduh {len(urls)} item…[/yellow]")
        self._download_worker(urls)

    # ------------------------------------------------------------------ workers
    @work(exclusive=True, thread=True)
    def _search_worker(self, kind: str, q: str, filters: dict) -> None:
        try:
            items, total = self.client.search(kind, q=q, filters=filters)
            self.call_from_thread(self._show_items, items, total)
        except ClosedError as e:
            self.call_from_thread(self._log, f"[yellow]⚠ {e}[/yellow]")
        except GdError as e:
            self.call_from_thread(self._log, f"[red]{e}[/red]")

    @work(exclusive=True, thread=True)
    def _login_worker(self) -> None:
        try:
            self.client.login()
            ok = self.client.is_logged_in()
            self.call_from_thread(self._log,
                                  "[green]Login berhasil ✓[/green]" if ok
                                  else "[yellow]Login gagal diverifikasi.[/yellow]")
        except GdError as e:
            self.call_from_thread(self._log, f"[red]{e}[/red]")
        finally:
            self.call_from_thread(self._set_status)

    @work(exclusive=True, thread=True)
    def _download_worker(self, urls) -> None:
        pb = self.query_one("#prog", ProgressBar)
        ok_files = 0
        for n, url in enumerate(urls, 1):
            self.call_from_thread(self._log, f"[blue]({n}/{len(urls)})[/blue] {url}")

            def cb(label, done, total, _n=n, _t=len(urls)):
                pct = int(done * 100 / total) if total else 0
                self.call_from_thread(pb.update, total=total or None, progress=done)
                self.call_from_thread(
                    self._set_status, f"· ({_n}/{_t}) {label[:24]} {pct}%")

            def log(m):
                self.call_from_thread(self._log, m)

            try:
                res = self.client.download_item(
                    url, self.out_dir, progress=cb, log=log)
                for r in res:
                    if r.get("status") == "ok":
                        ok_files += 1
            except GdError as e:
                self.call_from_thread(self._log, f"[red]{e}[/red]")
        self.call_from_thread(
            self._log, f"[green]Selesai: {ok_files} berkas diunduh ke {self.out_dir}[/green]")
        self.call_from_thread(self._set_status, "· selesai")


def run_tui(args) -> None:
    GdTui(args).run()
