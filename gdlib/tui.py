"""Textual TUI for gdlib-dl — dirancang agar enak dipakai.

Alur kerja: pilih koleksi + kata kunci di baris atas, saring lewat tombol
filter (jurusan/fakultas dibuka sebagai picker yang bisa dicari), lihat detail
di kanan, lalu unduh item atau seluruh halaman.
"""
from __future__ import annotations

import math
import os

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    ProgressBar,
    RichLog,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from .api import (
    JENIS,
    KIND_LABEL,
    KINDS,
    AuthError,
    ClosedError,
    GdError,
    GunadarmaClient,
    jurusan_group_of,
    label_for_jurusan,
    normalize_url,
    search_jurusan,
)

KIND_CHOICES = [(KIND_LABEL[k], k) for k in KINDS]
JENIS_CHOICES = [("Semua jenis", "")] + [(name, code) for name, code in JENIS.items()]

PER_PAGE = 20  # jumlah item per halaman di situs


# --------------------------------------------------------------------- modals
class JurusanModal(ModalScreen):
    """Picker jurusan/fakultas: ketik untuk menyaring, Enter untuk memilih."""

    BINDINGS = [("escape", "dismiss_none", "Batal")]

    def __init__(self, current: str = ""):
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="jbox"):
            yield Label("Pilih Jurusan / Fakultas", id="jtitle")
            yield Input(placeholder="ketik untuk mencari… (mis. info, ekon, psikologi)",
                        id="jq")
            yield OptionList(id="jlist")
            with Horizontal(id="jactions"):
                yield Button("Tutup (Esc)", id="jclose")

    def on_mount(self) -> None:
        self._fill("")
        self.query_one("#jq", Input).focus()

    def _fill(self, q: str) -> None:
        ol = self.query_one("#jlist", OptionList)
        ol.clear_options()
        results = search_jurusan(q, limit=200)
        if not results:
            ol.add_option(Option("(tidak ada yang cocok)", id="__none__"))
            return
        opts = []
        last_group = None
        for name, val in results:
            if not q.strip():
                group = jurusan_group_of(val)
                if group and group != last_group:
                    opts.append(Option(f"── {group} ──", id=f"__g_{group}",
                                       disabled=True))
                    last_group = group
            mark = "  ✓" if val == self.current else ""
            opts.append(Option(f"{name}{mark}", id=val))
        ol.add_options(opts)

    @on(Input.Changed, "#jq")
    def _changed(self, event: Input.Changed) -> None:
        self._fill(event.value)

    @on(Input.Submitted, "#jq")
    def _submitted(self, event: Input.Submitted) -> None:
        ol = self.query_one("#jlist", OptionList)
        for i in range(ol.option_count):
            opt = ol.get_option_at_index(i)
            if opt.id and not str(opt.id).startswith("__"):
                self._choose(opt)
                return

    @on(OptionList.OptionSelected, "#jlist")
    def _selected(self, event: OptionList.OptionSelected) -> None:
        self._choose(event.option)

    def _choose(self, option) -> None:
        if option is None or option.id is None:
            return
        if str(option.id).startswith("__"):
            return
        self.dismiss(option.id)

    @on(Button.Pressed, "#jclose")
    def _close(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class AdvancedModal(ModalScreen):
    """Filter lanjutan: NPM, penulis, pembimbing, nomor induk."""

    BINDINGS = [("escape", "dismiss_none", "Batal")]

    def __init__(self, values: dict):
        super().__init__()
        self.values = values or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="abox"):
            yield Label("Filter Lanjutan (Repository)", id="atitle")
            yield Label("NPM", classes="alabel")
            yield Input(value=self.values.get("npm", ""), placeholder="mis. 50422108",
                        id="a_npm")
            yield Label("Penulis", classes="alabel")
            yield Input(value=self.values.get("penulis", ""), placeholder="nama penulis…",
                        id="a_penulis")
            yield Label("Pembimbing", classes="alabel")
            yield Input(value=self.values.get("pembimbing", ""),
                        placeholder="nama pembimbing…", id="a_pembimbing")
            yield Label("Nomor Induk", classes="alabel")
            yield Input(value=self.values.get("nomor_induk", ""),
                        placeholder="nomor induk…", id="a_nomor")
            with Horizontal(id="aactions"):
                yield Button("Simpan", id="asave", variant="primary")
                yield Button("Batal (Esc)", id="acancel")

    def on_mount(self) -> None:
        self.query_one("#a_npm", Input).focus()

    @on(Button.Pressed, "#asave")
    def _save(self) -> None:
        self.dismiss({
            "npm": self.query_one("#a_npm", Input).value.strip(),
            "penulis": self.query_one("#a_penulis", Input).value.strip(),
            "pembimbing": self.query_one("#a_pembimbing", Input).value.strip(),
            "nomor_induk": self.query_one("#a_nomor", Input).value.strip(),
        })

    @on(Button.Pressed, "#acancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


# ------------------------------------------------------------------------ app
class GdTui(App):
    CSS = """
    Screen { layout: vertical; }

    #searchbar { height: 3; dock: top; padding: 0 1; }
    #searchbar Select { width: 34; }
    #searchbar Input { width: 1fr; }
    #searchbar Button { width: 12; margin: 0 0 0 1; }

    #filterbar { height: 3; padding: 0 1; }
    #filterbar .flabel { width: auto; padding: 1 1 0 0; color: $text-muted; }
    #filterbar Button { width: auto; min-width: 18; margin: 0 1 0 0; }
    #filterbar Select { width: 26; }
    #filterbar Input { width: 10; }

    #chips { height: 1; padding: 0 2; color: $accent; }

    #main { height: 1fr; }
    #left { width: 3fr; }
    #right { width: 2fr; border-left: solid $panel; padding: 0 1; }
    #results { height: 1fr; }
    #detail { padding: 1; }
    #bottom { height: 7; border-top: solid $panel; }
    #prog { height: 1; }
    #log { height: 1fr; }
    #status { dock: bottom; height: 1; padding: 0 1; color: $text-muted; }

    JurusanModal { align: center middle; }
    #jbox { width: 76; height: 34; border: round $accent; background: $surface;
            padding: 1 2; }
    #jtitle { text-style: bold; padding-bottom: 1; }
    #jlist { height: 1fr; border: round $panel; }
    #jactions { height: 3; align-horizontal: right; }

    AdvancedModal { align: center middle; }
    #abox { width: 60; height: auto; border: round $accent; background: $surface;
            padding: 1 2; }
    #atitle { text-style: bold; padding-bottom: 1; }
    .alabel { color: $text-muted; padding-top: 1; }
    #aactions { height: 3; align-horizontal: right; padding-top: 1; }
    #aactions Button { margin-left: 1; }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Keluar"),
        ("f1", "login", "Login"),
        ("f2", "open_jurusan", "Jurusan"),
        ("f3", "open_advanced", "Filter+"),
        ("f4", "reset_filters", "Reset filter"),
        ("f5", "do_search", "Cari"),
        ("f6", "prev_page", "◀ Hal."),
        ("f7", "next_page", "Hal. ▶"),
        ("f9", "download_selected", "Unduh item"),
        ("f10", "download_all", "Unduh halaman"),
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
        self.total = None
        self.page = 1
        self.current_kind = "repository"
        # state filter (repository)
        self.filters: dict = {}
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
            yield Static("Filter:", classes="flabel")
            yield Button("Fakultas/Jurusan…", id="btn_jurusan")
            yield Select(JENIS_CHOICES, value="", id="f_jenis")
            yield Input(placeholder="tahun", id="f_tahun")
            yield Button("Filter lain…", id="btn_adv")
            yield Button("Reset", id="btn_reset", variant="warning")
        yield Static("", id="chips")
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
        t.add_columns("#", "Jenis", "Judul", "Penulis/NPM", "Tahun", "Dilihat")
        self._log("gdlib-dl TUI siap. [b]/[/b] cari · [b]F2[/b] jurusan · "
                  "[b]F3[/b] filter lain · [b]F5[/b] cari · [b]F9[/b] unduh item · "
                  "[b]F10[/b] unduh halaman.")
        self._log("[dim]Filter jurusan/jenis/tahun berlaku untuk koleksi "
                  "Repository. E-Paper & E-Book perlu login (F1).[/dim]")
        for m in self._pending:
            self._log(m)
        self._pending.clear()
        self._refresh_chips()
        self._set_status()

    # ------------------------------------------------------------------- helpers
    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    def _set_status(self, extra: str = "") -> None:
        who = self.client.username or "(belum login)"
        st = "login ✓" if self.client.logged_in else "belum login"
        page = ""
        if self.items:
            n_pages = self._n_pages()
            page = f" · hal. {self.page}" + (f"/{n_pages}" if n_pages else "")
        self.query_one("#status", Static).update(
            f"user: {who} · {st} · tujuan: {self.out_dir}{page} {extra}"
        )

    def _n_pages(self) -> int:
        if self.total and self.items:
            return max(1, math.ceil(self.total / max(1, len(self.items))))
        return 0

    def _kind(self) -> str:
        v = self.query_one("#kind", Select).value
        return v if isinstance(v, str) else "repository"

    def _active_filters(self) -> dict:
        """Bangun dict filter yang dikirim ke server (hanya untuk repository)."""
        f = dict(self.filters)
        jen = self.query_one("#f_jenis", Select).value
        thn = self.query_one("#f_tahun", Input).value.strip()
        if isinstance(jen, str) and jen:
            f["jenis"] = jen
        else:
            f.pop("jenis", None)
        if thn:
            f["tahun"] = thn
        else:
            f.pop("tahun", None)
        return {k: v for k, v in f.items() if v}

    def _refresh_chips(self) -> None:
        f = self._active_filters()
        if not f:
            self.query_one("#chips", Static).update(
                "[dim]Tidak ada filter aktif — menampilkan semua.[/dim]")
            return
        parts = []
        if f.get("jurusan"):
            parts.append(f"Jurusan: [b]{label_for_jurusan(f['jurusan'])}[/b]")
        if f.get("jenis"):
            parts.append(f"Jenis: [b]{f['jenis']}[/b]")
        if f.get("tahun"):
            parts.append(f"Tahun: [b]{f['tahun']}[/b]")
        if f.get("npm"):
            parts.append(f"NPM: [b]{f['npm']}[/b]")
        if f.get("penulis"):
            parts.append(f"Penulis: [b]{f['penulis']}[/b]")
        if f.get("pembimbing"):
            parts.append(f"Pembimbing: [b]{f['pembimbing']}[/b]")
        if f.get("nomor_induk"):
            parts.append(f"No. Induk: [b]{f['nomor_induk']}[/b]")
        self.query_one("#chips", Static).update("Filter aktif → " + "  ·  ".join(parts))

    def _show_items(self, items, total) -> None:
        self.items = items
        self.total = total
        t = self.query_one("#results", DataTable)
        t.clear()
        for i, it in enumerate(items, 1):
            t.add_row(str(i), it.tag or it.kind, it.title[:90],
                      it.author[:24], it.year, it.views, key=str(i - 1))
        extra = f"· {len(items)} hasil"
        if total:
            extra += f" dari {total:,}"
        self._set_status(extra)
        self._log(f"[cyan]{len(items)} item ditampilkan"
                  + (f" dari total {total:,}" if total else "")
                  + f" · halaman {self.page}[/cyan]")
        if items:
            t.move_cursor(row=0)
            self._show_detail(items[0])
        else:
            self.query_one("#detail", Static).update(
                "Tidak ada hasil. Coba kata kunci lain atau kurangi filter.")

    def _show_detail(self, item) -> None:
        lines = [f"[bold]{item.title}[/bold]"]
        if item.author:
            lines.append(f"[dim]Penulis/NPM:[/dim] {item.author}")
        if item.year:
            lines.append(f"[dim]Tahun:[/dim] {item.year}")
        if item.views:
            lines.append(f"[dim]{item.views}[/dim]")
        lines.append(f"[dim]Jenis:[/dim] {item.tag or item.kind}")
        lines.append(f"[dim]URL:[/dim] {item.url}")
        if item.abstract:
            lines.append("")
            lines.append(item.abstract[:800])
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
        self._refresh_chips()
        self.action_do_search()

    @on(Select.Changed, "#f_jenis")
    def _jenis_changed(self, event: Select.Changed) -> None:
        self._refresh_chips()

    @on(Button.Pressed, "#btn_search")
    def _btn_search(self, event: Button.Pressed) -> None:
        self.action_do_search()

    @on(Button.Pressed, "#btn_jurusan")
    def _btn_jurusan(self, event: Button.Pressed) -> None:
        self.action_open_jurusan()

    @on(Button.Pressed, "#btn_adv")
    def _btn_adv(self, event: Button.Pressed) -> None:
        self.action_open_advanced()

    @on(Button.Pressed, "#btn_reset")
    def _btn_reset(self, event: Button.Pressed) -> None:
        self.action_reset_filters()

    def action_focus_search(self) -> None:
        self.query_one("#query", Input).focus()

    # -------------------------------------------------------------- filter actions
    def action_open_jurusan(self) -> None:
        def cb(value) -> None:
            if value is None:
                return
            self.filters["jurusan"] = value
            self._refresh_chips()
            self._log(f"[green]Filter jurusan:[/green] {label_for_jurusan(value)}")
            self.action_do_search()
        self.push_screen(JurusanModal(self.filters.get("jurusan", "")), cb)

    def action_open_advanced(self) -> None:
        def cb(values) -> None:
            if values is None:
                return
            for k in ("npm", "penulis", "pembimbing", "nomor_induk"):
                if values.get(k):
                    self.filters[k] = values[k]
                else:
                    self.filters.pop(k, None)
            self._refresh_chips()
            self.action_do_search()
        self.push_screen(AdvancedModal(self.filters), cb)

    def action_reset_filters(self) -> None:
        self.filters = {}
        self.query_one("#f_jenis", Select).value = ""
        self.query_one("#f_tahun", Input).value = ""
        self._refresh_chips()
        self._log("[yellow]Filter direset.[/yellow]")
        self.action_do_search()

    # ---------------------------------------------------------------- search/page
    def _run_search(self, page: int) -> None:
        q = self.query_one("#query", Input).value.strip()
        kind = self._kind()
        self.current_kind = kind
        self.page = page
        filters = self._active_filters() if kind == "repository" else {}
        self._log(f"[yellow]Mencari[/yellow] '{q}' di {KIND_LABEL[kind]}"
                  + (f" · filter {filters}" if filters else "")
                  + f" · halaman {page} …")
        self._search_worker(kind, q, filters, page)

    def action_do_search(self) -> None:
        self._run_search(1)

    def action_next_page(self) -> None:
        n = self._n_pages()
        if n and self.page >= n:
            self._log("[yellow]Sudah di halaman terakhir.[/yellow]")
            return
        self._run_search(self.page + 1)

    def action_prev_page(self) -> None:
        if self.page <= 1:
            self._log("[yellow]Sudah di halaman pertama.[/yellow]")
            return
        self._run_search(self.page - 1)

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
        self._log(f"[yellow]Mengunduh {len(urls)} item (halaman ini)…[/yellow]")
        self._download_worker(urls)

    # ------------------------------------------------------------------ workers
    @work(exclusive=True, thread=True)
    def _search_worker(self, kind: str, q: str, filters: dict, page: int) -> None:
        try:
            items, total = self.client.search(kind, q=q, page=page, filters=filters)
            self.call_from_thread(self._show_items, items, total)
        except ClosedError as e:
            self.call_from_thread(self._log, f"[yellow]⚠ {e}[/yellow]")
        except AuthError as e:
            self.call_from_thread(self._log, f"[red]{e} Coba F1 untuk login.[/red]")
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
