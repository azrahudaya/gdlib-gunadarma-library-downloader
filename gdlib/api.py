"""
Core client for library.gunadarma.ac.id (Universitas Gunadarma Library).

Verified against the live site:

* Login is Laravel-based: GET /login -> parse <input name="_token"> + session
  cookies, then POST /login with fields `nomor_anggota` (NPM/NIP) + `password`.
  No captcha. Wrong credentials return "Akses login gagal".

* Search results are server-rendered fragments; requesting them with header
  `X-Requested-With: XMLHttpRequest` returns just the results block.

* Repository (PI/Skripsi/Tesis/Disertasi) detail lists files in two flavours:
    - "Akses Terbuka" -> direct link /repository/file/<id>?token=... (needs the
      SAME session that fetched the detail page).
    - "Akses Kampus"  -> the href points at the E-Paper reader
      /epaper/<key>. The real PDF is fetched from /epaper/fid/<fid>, where the
      fid is exposed in the reader page as `data-id` on each button.toc-btn.
      Both require being logged in.

* E-Book reader /ebooks/<slug>/baca exposes <div id="readSessionMeta"
  data-pdf-url="..."> -> the e-book PDF. Requires login.

* E-Paper (/epaper) is a searchable collection of the same scholarly works with
  a built-in reader; requires login.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable, Optional

import requests
from bs4 import BeautifulSoup

BASE = "https://library.gunadarma.ac.id"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

KINDS = ("repository", "epaper", "ebooks", "journal", "catalog")
KIND_LABEL = {
    "repository": "Repository (PI/Skripsi/Tesis/Disertasi)",
    "epaper": "E-Paper (karya ilmiah, perlu login)",
    "ebooks": "E-Book UG (perlu login)",
    "journal": "Jurnal Ilmiah",
    "catalog": "Katalog OPAC (metadata)",
}

# Jenis penulisan (filter `jenis`)
JENIS = {
    "Semua jenis": "",
    "DISERTASI": "disertasi",
    "PENELITIAN HIBAH": "hibah",
    "PENULISAN ILMIAH JENJANG D3": "pi",
    "PENULISAN ILMIAH JENJANG S1 (SETARA SARJANA MUDA / SSM)": "ssm",
    "PENULISAN/PENELITIAN DOSEN": "penelitian",
    "SKRIPSI": "skripsi",
    "TESIS": "tesis",
}

# Jurusan / fakultas (filter `jurusan`), lengkap 96 opsi & dikelompokkan
# persis seperti <optgroup> di situs. Urutan grup: prodi dulu, lalu "Semua X".
JURUSAN_GROUPS: dict[str, list[tuple[str, str]]] = {
    "Ilmu Komputer & Teknologi Informasi": [
        ("Manajemen Informatika (D3)", "16"),
        ("Sistem Informasi (S1)", "1"),
        ("Sistem Komputer (S1)", "2"),
        ("Teknik Komputer (D3)", "11"),
        ("Informatika (S1)", "6"),
    ],
    "Teknologi Industri": [
        ("Agroteknologi (S1)", "42"),
        ("Informatika (S1)", "6"),
        ("Teknik Elektro (S1)", "4"),
        ("Teknik Industri (S1)", "3"),
        ("Teknik Mesin (S1)", "5"),
    ],
    "Teknik Sipil & Perencanaan": [
        ("Desain Interior (S1)", "17"),
        ("Teknik Arsitektur (S1)", "8"),
        ("Teknik Sipil (S1)", "7"),
    ],
    "Ekonomi": [
        ("Akuntansi (S1)", "13"),
        ("Akuntansi Komputer (D3)", "19"),
        ("Ekonomi Syariah (S1)", "40"),
        ("Manajemen (S1)", "12"),
        ("Manajemen Keuangan (D3)", "37"),
        ("Manajemen Pemasaran (D3)", "18"),
    ],
    "Psikologi": [
        ("Psikologi (S1)", "15"),
    ],
    "Sastra & Budaya": [
        ("Pariwisata (S1)", "39"),
        ("Sastra Inggris (S1)", "14"),
        ("Sastra Tiongkok (S1)", "41"),
    ],
    "Ilmu Komunikasi": [
        ("Komunikasi (S1)", "32"),
    ],
    "Ilmu Kesehatan & Farmasi": [
        ("Farmasi (S1)", "43"),
    ],
    "Kedokteran": [
        ("Kedokteran (S1)", "38"),
    ],
    "Akademi Kebidanan": [
        ("Kebidanan (S1)", "9"),
    ],
    "Magister Manajemen Sistem Informasi": [
        ("Pengembangan Produk dan Desain (S2)", "46"),
        ("Perangkat Lunak Sistem Informasi (S2)", "25"),
        ("Sistem Informasi Akuntansi (S2)", "22"),
        ("Sistem Informasi Bisnis (S2)", "21"),
        ("Teknik Informasi Pertanian (S2)", "65"),
    ],
    "Magister Teknik Elektro": [
        ("Elektronika Devais (S2)", "47"),
        ("Elektronika Telekomunikasi (S2)", "23"),
        ("Teknik Kontrol Industri (S2)", "48"),
        ("Teknologi Informasi (S2)", "49"),
    ],
    "Magister Manajemen": [
        ("Akuntansi Pemerintahan (S2)", "27"),
        ("Asuransi (S2)", "20"),
        ("Keuangan Syariah (S2)", "100"),
        ("Komunikasi Bisnis (S2)", "45"),
        ("Manajemen Pemasaran (S2)", "101"),
        ("Manajemen Sumber Daya Manusia (S2)", "64"),
        ("Perbankan (S2)", "28"),
    ],
    "Magister Ilmu Komunikasi": [
        ("Ilmu Komunikasi Pendidikan (S2)", "60"),
        ("Komunikasi Pariwisata (S2)", "68"),
        ("Komunikasi Pemasaran (S2)", "63"),
        ("Komunikasi Politik (S2)", "44"),
        ("Marketing Komunikasi (S2)", "59"),
        ("Teknologi dan New Media (S2)", "58"),
    ],
    "Magister Psikologi": [
        ("Psikologi Industri dan Organisasi (S2)", "34"),
        ("Psikologi Industri dan Organisasi Profesi (S2)", "53"),
        ("Psikologi Klinis Profesi (S2)", "35"),
        ("Psikologi Komunikasi (S2)", "26"),
    ],
    "Magister Sastra": [
        ("Kajian Budaya (S2)", "102"),
        ("Penerjemahan (S2)", "24"),
    ],
    "Magister Teknik Arsitektur": [
        ("Desain Arsitektur (S2)", "61"),
        ("Riset Arsitektur dan Perkotaan (S2)", "62"),
    ],
    "Magister Teknik Industri & Manajemen": [
        ("Teknik Industri dan Manajemen (S2)", "66"),
    ],
    "Magister Teknik Mesin": [
        ("Rekayasa Manufaktur Aditif (S2)", "57"),
        ("Rekayasa Sistem Energi (S2)", "56"),
        ("Rekayasa Sistem Manufaktur (S2)", "33"),
    ],
    "Magister Teknik Sipil": [
        ("Arsitektur dan Perkotaan (S2)", "31"),
        ("Manajemen Rekayasa Infrastruktur (S2)", "50"),
        ("Sistem Informasi Infrastruktur (S2)", "51"),
    ],
    "Doktor Teknologi Informasi": [
        ("Teknologi Informasi (S3)", "30"),
    ],
    "Doktor Ilmu Ekonomi": [
        ("Ilmu Ekonomi (S3)", "29"),
    ],
    "Doktor Ilmu Komunikasi": [
        ("Ilmu Komunikasi (S3)", "67"),
    ],
    "Doktor Psikologi": [
        ("Psikologi (S3)", "36"),
    ],
    "Lainnya": [
        ("Paket (88)", "10"),
        ("Tidak Terkategori (99)", "99"),
    ],
}

# Nama jurusan -> id (flatten dari grup).
JURUSAN: dict[str, str] = {
    name: jid for progs in JURUSAN_GROUPS.values() for name, jid in progs
}

# Nama -> value untuk resolve & tampilan.
JURUSAN_ANY: dict[str, str] = dict(JURUSAN)

# Alias pencarian populer (biar "informatika"/"if" tetap nemu prodi yang tepat).
JURUSAN_ALIAS: dict[str, str] = {
    "informatika": "6",
    "if": "6",
    "si": "1",
    "sk": "2",
    "tk": "11",
    "mi": "16",
    "d3 mi": "16",
    "manajemen informatika": "16",
}


def jurusan_group_of(value: str) -> str:
    """Nama grup untuk sebuah value jurusan (untuk header di picker)."""
    for group, progs in JURUSAN_GROUPS.items():
        if any(jid == value for _, jid in progs):
            return group
    return ""




class GdError(Exception):
    pass


class AuthError(GdError):
    pass


class NotFoundError(GdError):
    pass


class RestrictedError(GdError):
    """File needs login (or another privilege) to be downloaded."""


class ClosedError(GdError):
    """Situs sedang di luar jam operasional akses publik (Jam Bebas Akses)."""


# Halaman "Jam Bebas Akses" muncul tiap 23:00-03:00 WIB dengan status 503.
_CLOSED_MARKERS = ("Jam Bebas Akses", "Free Time", "di luar jam operasional")


def _looks_closed(status: int, text: str) -> bool:
    if status == 503:
        return True
    return any(m in text for m in _CLOSED_MARKERS)


def _closed_message(text: str) -> str:
    m = re.search(r"(\d{2}:\d{2})\s*[—\-–]\s*(\d{2}:\d{2})", text)
    jadwal = f" ({m.group(1)}–{m.group(2)} WIB)" if m else " (23:00–03:00 WIB)"
    return ("Perpustakaan sedang di luar jam operasional akses publik "
            f"\"Jam Bebas Akses\"{jadwal}. Coba lagi setelah jam tersebut.")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def resolve_jurusan(value: str) -> str:
    """Terima nama jurusan/fakultas atau id; kembalikan value server."""
    if not value:
        return ""
    v = value.strip()
    if v in JURUSAN_ANY:
        return JURUSAN_ANY[v]
    if re.fullmatch(r"fak_\d+", v) or re.fullmatch(r"\d+", v):
        return v
    low = v.lower()
    if low in JURUSAN_ALIAS:
        return JURUSAN_ALIAS[low]
    for name, jid in JURUSAN_ANY.items():
        if low in name.lower():
            return jid
    return value


def label_for_jurusan(value: str) -> str:
    """Kebalikannya: value server -> nama yang enak dibaca (untuk chip filter)."""
    if not value:
        return ""
    for name, jid in JURUSAN_ANY.items():
        if jid == value:
            return name
    return value


def search_jurusan(query: str, limit: int = 40) -> list[tuple[str, str]]:
    """Cari opsi jurusan/fakultas untuk picker.

    Kembalikan list (nama, value) dengan peringkat: awalan nama > nama
    mengandung > alias cocok. Mengembalikan semua bila query kosong.
    """
    q = (query or "").strip().lower()
    entries = list(JURUSAN_ANY.items())
    if not q:
        return entries[:limit]
    scored: list[tuple[int, str, str]] = []
    alias_hit = JURUSAN_ALIAS.get(q)
    for name, val in entries:
        n = name.lower()
        if n.startswith(q):
            score = 0
        elif q in n:
            score = 1
        else:
            score = 9
        if alias_hit and val == alias_hit:
            score = min(score, 0)
        if score < 9:
            scored.append((score, name, val))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [(n, v) for _, n, v in scored[:limit]]


def resolve_jenis(value: str) -> str:
    if not value:
        return ""
    if value in JENIS.values():
        return value
    for name, jid in JENIS.items():
        if value.lower() in name.lower():
            return jid
    return value


@dataclass
class Item:
    kind: str
    title: str
    url: str
    id: str = ""
    author: str = ""
    year: str = ""
    views: str = ""
    tag: str = ""
    abstract: str = ""
    files: list = field(default_factory=list)  # [{label,url,access}]

    def to_dict(self) -> dict:
        return asdict(self)

    def slug(self) -> str:
        s = re.sub(r"[^\w\-]+", "_", self.title.strip())[:80].strip("_")
        return s or self.id or "item"


class GunadarmaClient:
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session_file: Optional[str] = None,
        timeout: int = 30,
    ):
        self.username = username
        self.password = password
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "id,en;q=0.9"})
        self.session_file = session_file or os.path.join(
            os.path.dirname(__file__), ".session.json"
        )
        self.logged_in = False
        self._load_session()

    # ------------------------------------------------------------------ session
    def _load_session(self) -> None:
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.get("cookies", {}).items():
                self.s.cookies.set(k, v, domain="library.gunadarma.ac.id")
            self.logged_in = bool(data.get("logged_in"))
        except Exception:
            pass

    def _save_session(self) -> None:
        try:
            cookies = {c.name: c.value for c in self.s.cookies}
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies, "logged_in": self.logged_in,
                           "username": self.username}, f)
            os.chmod(self.session_file, 0o600)
        except Exception:
            pass

    def clear_session(self) -> None:
        self.s.cookies.clear()
        self.logged_in = False
        try:
            os.remove(self.session_file)
        except OSError:
            pass

    # -------------------------------------------------------------------- login
    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        force: bool = False,
    ) -> bool:
        u = username or self.username
        p = password or self.password
        if not u or not p:
            raise AuthError(
                "Nomor anggota / password belum diisi. Isi file .env "
                "(GDLIB_USERNAME, GDLIB_PASSWORD) atau pakai --username/--password."
            )
        r = self.s.get(f"{BASE}/login", timeout=self.timeout)
        if _looks_closed(r.status_code, r.text):
            raise ClosedError(_closed_message(r.text))
        soup = BeautifulSoup(r.text, "html.parser")
        tok = soup.select_one('form input[name="_token"]')
        if not tok:
            raise AuthError("Tidak menemukan token login (struktur halaman berubah?).")
        data = {"_token": tok.get("value", ""), "nomor_anggota": u, "password": p}
        r = self.s.post(f"{BASE}/login", data=data,
                        headers={"Referer": f"{BASE}/login"}, timeout=self.timeout)
        if _looks_closed(r.status_code, r.text):
            raise ClosedError(_closed_message(r.text))
        if "Akses login gagal" in r.text or 'name="password"' in r.text:
            self.logged_in = False
            raise AuthError("Login gagal: periksa nomor anggota / password.")
        self.logged_in = True
        self.username = u
        self._save_session()
        return True

    def is_logged_in(self) -> bool:
        if not self.logged_in:
            return False
        try:
            r = self.s.get(f"{BASE}/epaper?tab=stats",
                           headers={"X-Requested-With": "XMLHttpRequest"},
                           timeout=self.timeout)
            if _looks_closed(r.status_code, r.text):
                # Situs tutup: sesi mungkin masih valid, jangan dianggap logout.
                return self.logged_in
            return r.status_code == 200
        except Exception:
            return self.logged_in

    def ensure_login(self) -> None:
        if not self.is_logged_in():
            self.login()

    # ------------------------------------------------------------------- search
    def search(self, kind: str, q: str = "", page: int = 1,
               filters: Optional[dict] = None) -> tuple[list[Item], Optional[int]]:
        if kind not in KINDS:
            raise GdError(f"kind tidak dikenal: {kind}")
        params: dict = {}
        if q:
            params["q"] = q
        if filters:
            params.update({k: v for k, v in filters.items() if v})
        if page and page > 1:
            params["page"] = page
        r = self.s.get(f"{BASE}/{kind}", params=params,
                       headers={"X-Requested-With": "XMLHttpRequest"},
                       timeout=self.timeout)
        if _looks_closed(r.status_code, r.text):
            raise ClosedError(_closed_message(r.text))
        if 'name="password"' in r.text or "/login" in r.url:
            raise AuthError(f"{kind} memerlukan login.")
        return self._parse_results(kind, r.text)

    def _parse_results(self, kind: str, html_text: str):
        soup = BeautifulSoup(html_text, "html.parser")
        items: list[Item] = []

        if kind in ("repository", "journal", "catalog"):
            for a in soup.select("a.pub-card"):
                url = a.get("href")
                if not url:
                    continue
                h3 = a.select_one("h3")
                tag_el = a.select_one(".tag")
                spans = [_clean(s.get_text()) for s in a.select(".meta-row span")]
                author = spans[0] if spans else ""
                year = next((s for s in spans if re.fullmatch(r"(19|20)\d{2}", s)), "")
                views = next((s for s in spans if "dilihat" in s.lower()), "")
                abst_el = a.select_one(".abst")
                isbn_el = a.select_one(".pub-card-isbn")
                items.append(Item(
                    kind=kind, title=_clean(h3.get_text()) if h3 else "", url=url,
                    id=url.rstrip("/").rsplit("/", 1)[-1],
                    author=author, year=year, views=views,
                    tag=_clean(tag_el.get_text()) if tag_el else "",
                    abstract=_clean(abst_el.get_text()) if abst_el else (
                        _clean(isbn_el.get_text()) if isbn_el else "")))
        elif kind == "ebooks":
            for a in soup.select("a.ebook-card-link"):
                url = a.get("href")
                if not url:
                    continue
                t_el = a.select_one(".ebook-card-title-alt")
                if t_el and t_el.get("title"):
                    title = _clean(t_el.get("title"))
                elif t_el:
                    title = _clean(t_el.get_text())
                else:
                    img = a.select_one("img")
                    title = _clean(img.get("alt")) if img else ""
                au = a.select_one(".ebook-card-author")
                items.append(Item(kind="ebooks", title=title, url=url,
                                  id=url.rstrip("/").rsplit("/", 1)[-1],
                                  author=_clean(au.get_text()) if au else ""))
        elif kind == "epaper":
            for a in soup.select("a[href*='/epaper/']"):
                url = a.get("href")
                card = a.find_parent(class_=re.compile("epaper-card"))
                if not url or not card:
                    continue
                h3 = card.select_one("h3")
                badge = card.select_one(".badge-jenis")
                author = ""
                for row in card.select("div.d-flex.gap-2"):
                    t = _clean(row.get_text())
                    if t.startswith("Penulis:"):
                        author = t.replace("Penulis:", "").strip()
                items.append(Item(
                    kind="epaper", title=_clean(h3.get_text()) if h3 else "", url=url,
                    id=url.rstrip("/").rsplit("/", 1)[-1][:40],
                    author=author,
                    tag=_clean(badge.get_text()) if badge else ""))

        total = None
        flat = _clean(BeautifulSoup(html_text, "html.parser").get_text(" "))
        m = re.search(r"([\d.,]+)\s*(?:karya|e-book|artikel|judul|hasil|e-paper)", flat)
        if m:
            try:
                total = int(re.sub(r"[.,]", "", m.group(1)))
            except ValueError:
                total = None
        return items, total

    def iter_search(self, kind: str, q: str = "", filters: Optional[dict] = None,
                    max_items: int = 50, max_pages: int = 500) -> Iterable[Item]:
        page = 1
        seen = 0
        while page <= max_pages:
            items, _ = self.search(kind, q=q, page=page, filters=filters)
            if not items:
                break
            for it in items:
                yield it
                seen += 1
                if seen >= max_items:
                    return
            page += 1

    # ------------------------------------------------------------------- detail
    def get_detail(self, item_or_url) -> Item:
        if isinstance(item_or_url, Item):
            item, url = item_or_url, item_or_url.url
        else:
            url = item_or_url
            item = Item(kind=self._kind_from_url(url), title="", url=url,
                        id=url.rstrip("/").rsplit("/", 1)[-1])
        r = self.s.get(url, timeout=self.timeout)
        if _looks_closed(r.status_code, r.text):
            raise ClosedError(_closed_message(r.text))
        if "/login" in r.url and 'name="password"' in r.text:
            raise AuthError(f"Perlu login untuk membuka: {url}")
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.select_one('meta[property="og:title"]')
        if og and og.get("content"):
            item.title = _clean(og.get("content")).split(" — ")[0]
        else:
            h = soup.select_one("h1, h2")
            if h:
                item.title = _clean(h.get_text())

        files = []
        for a in soup.select("a.btn-doc-action"):
            href = a.get("href") or a.get("data-src")
            if not href:
                continue
            label = access = ""
            for anc in a.parents:
                if not label:
                    t = anc.select_one(".doc-title")
                    if t:
                        label = _clean(t.get_text())
                if not access:
                    b = anc.select_one(".doc-badge")
                    if b:
                        access = _clean(b.get_text())
                if label and access:
                    break
                if anc.name == "body":
                    break
            files.append({"label": label or "DOKUMEN", "url": href, "access": access})
        item.files = files
        return item

    @staticmethod
    def _kind_from_url(url: str) -> str:
        if "/ebooks/" in url:
            return "ebooks"
        if "/journal/" in url:
            return "journal"
        if "/catalog/" in url:
            return "catalog"
        if "/epaper/" in url:
            return "epaper"
        return "repository"

    # -------------------------------------------------------------- e-paper fid
    def epaper_toc(self, reader_url: str) -> dict[str, str]:
        """Ambil peta {label: fid} dari halaman reader e-paper."""
        r = self.s.get(reader_url, timeout=self.timeout)
        if _looks_closed(r.status_code, r.text):
            raise ClosedError(_closed_message(r.text))
        if "/login" in r.url:
            raise AuthError("E-Paper memerlukan login.")
        soup = BeautifulSoup(r.text, "html.parser")
        toc = {}
        for b in soup.select("button.toc-btn"):
            label = _clean(b.get_text())
            fid = b.get("data-id")
            if label and fid:
                toc[label] = fid
        return toc

    def epaper_fid_url(self, fid: str) -> str:
        return f"{BASE}/epaper/fid/{fid}"

    # ------------------------------------------------------------ ebook journal
    def ebook_pdf_url(self, item_or_url) -> str:
        url = item_or_url.url if isinstance(item_or_url, Item) else item_or_url
        baca = url.rstrip("/") + "/baca"
        r = self.s.get(baca, timeout=self.timeout)
        if _looks_closed(r.status_code, r.text):
            raise ClosedError(_closed_message(r.text))
        if "/login" in r.url:
            raise AuthError("E-book memerlukan login.")
        soup = BeautifulSoup(r.text, "html.parser")
        meta = soup.select_one("#readSessionMeta")
        if not meta:
            if 'name="password"' in r.text:
                raise AuthError("E-book memerlukan login.")
            raise NotFoundError("Tidak menemukan sumber PDF e-book.")
        src = meta.get("data-pdf-url")
        if not src:
            raise NotFoundError("data-pdf-url kosong.")
        return src

    def journal_pdf_url(self, item_or_url) -> Optional[str]:
        url = item_or_url.url if isinstance(item_or_url, Item) else item_or_url
        r = self.s.get(url, timeout=self.timeout)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href]"):
            href = a["href"]
            if re.search(r"/(?:journal/)?file/", href) or href.lower().endswith(".pdf"):
                return href
        return None

    # ---------------------------------------------------------------- download
    def download(self, url: str, dest_dir: str, filename: Optional[str] = None,
                 referer: Optional[str] = None,
                 progress: Optional[Callable[[int, int], None]] = None,
                 ) -> tuple[str, str]:
        headers = {}
        if referer:
            headers["Referer"] = referer
        with self.s.get(url, headers=headers, stream=True, timeout=self.timeout) as r:
            if r.status_code == 503:
                raise ClosedError("Perpustakaan sedang di luar jam operasional akses "
                                  "publik (Jam Bebas Akses, 23:00–03:00 WIB).")
            if r.status_code in (401, 403):
                raise AuthError(f"Akses ditolak ({r.status_code}). Login dulu "
                                "atau buka lewat halaman detail.")
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            base_ctype = ctype.split(";")[0].strip().lower()
            if base_ctype in ("text/html", "application/xhtml+xml"):
                raise RestrictedError(
                    "Server mengembalikan halaman HTML, bukan berkas. "
                    "Berkas ini butuh login / akses khusus.")
            if filename is None:
                filename = self._filename_from(r, url)
            else:
                filename = self._ensure_ext(filename, base_ctype)
            os.makedirs(dest_dir, exist_ok=True)
            dest = _dedupe_path(os.path.join(dest_dir, filename))
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            os.replace(tmp, dest)
            return dest, ctype

    @staticmethod
    def _ensure_ext(filename: str, base_ctype: str) -> str:
        ext = {
            "application/pdf": ".pdf",
            "application/zip": ".zip",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        }.get(base_ctype, "")
        if ext and not filename.lower().endswith((".pdf", ".doc", ".docx", ".zip")):
            filename += ext
        return filename

    @staticmethod
    def _filename_from(resp, url: str) -> str:
        cd = resp.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^\";]+)"?', cd)
        if m:
            from urllib.parse import unquote
            return unquote(m.group(1))
        base = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] or "file"
        return GunadarmaClient._ensure_ext(
            base, resp.headers.get("Content-Type", "").split(";")[0].strip().lower())

    # ----------------------------------------------------- high level download
    def download_item(self, url: str, out_dir: str,
                      which: Optional[set[int]] = None,
                      progress: Optional[Callable[[str, int, int], None]] = None,
                      log: Callable[[str], None] = print) -> list[dict]:
        kind = self._kind_from_url(url)
        if kind == "catalog":
            item = self.get_detail(url)
            log(f"[katalog] {item.title} — hanya metadata, tidak ada file.")
            return [{"kind": kind, "title": item.title, "status": "metadata-only"}]
        if kind == "epaper":
            return self._download_epaper_item(url, out_dir, progress, log)
        if kind == "repository":
            return self._download_repository(url, out_dir, which, progress, log)
        if kind == "ebooks":
            return self._download_ebook(url, out_dir, progress, log)
        if kind == "journal":
            return self._download_journal(url, out_dir, log)
        raise GdError(f"Jenis tidak didukung: {kind}")

    def _download_repository(self, url, out_dir, which, progress, log):
        item = self.get_detail(url)
        if not item.files:
            log(f"[repository] {item.title}: tidak ada file.")
            return []
        # Saat belum login, berkas "Akses Kampus" tampil sebagai
        # /login?return_url=... . Login dulu lalu ambil ulang detail.
        if any("/login" in f["url"] for f in item.files) and self.username and self.password:
            try:
                self.login()
                item = self.get_detail(url)
            except GdError as e:
                log(f"  ! login untuk berkas terbatas gagal: {e}")
        # Ambil peta fid e-paper sekali bila ada berkas lewat reader.
        toc = None
        reader_url = None
        for f in item.files:
            if "/epaper/" in f["url"]:
                reader_url = f["url"]
                break
        if reader_url:
            try:
                toc = self.epaper_toc(reader_url)
            except GdError as e:
                log(f"  ! tidak bisa membuka reader e-paper: {e}")

        results = []
        for i, f in enumerate(item.files):
            if which and i not in which:
                continue
            label = f["label"]
            fname = f"{i+1:02d}_" + re.sub(r"[^\w\-]+", "_", label)[:60].strip("_")
            try:
                href = f["url"]
                if "/repository/file/" in href:
                    path, _ = self.download(
                        href, out_dir, filename=fname, referer=url,
                        progress=(lambda d, t, _l=label: progress(_l, d, t)) if progress else None)
                elif "/epaper/" in href:
                    fid = (toc or {}).get(label)
                    if not fid:
                        raise NotFoundError("berkas tidak tersedia di reader e-paper.")
                    path, _ = self.download(
                        self.epaper_fid_url(fid), out_dir, filename=fname,
                        referer=reader_url,
                        progress=(lambda d, t, _l=label: progress(_l, d, t)) if progress else None)
                elif "/login" in href:
                    raise AuthError("perlu login untuk berkas ini (cek .env).")
                else:
                    raise NotFoundError("jenis tautan tidak dikenal.")
                log(f"  ✓ {label} -> {os.path.basename(path)}")
                results.append({"kind": "repository", "title": item.title,
                                "label": label, "path": path, "status": "ok"})
            except Exception as e:  # noqa: BLE001
                log(f"  ✗ {label}: {e}")
                results.append({"kind": "repository", "title": item.title,
                                "label": label, "status": "error", "error": str(e)})
        return results

    def _download_epaper_item(self, url, out_dir, progress, log):
        try:
            toc = self.epaper_toc(url)
        except GdError as e:
            log(f"[e-paper] {e}")
            return [{"kind": "epaper", "url": url, "status": "error", "error": str(e)}]
        if not toc:
            log(f"[e-paper] {url}: tidak ada berkas.")
            return []
        results = []
        for i, (label, fid) in enumerate(toc.items(), 1):
            fname = f"{i:02d}_" + re.sub(r"[^\w\-]+", "_", label)[:60].strip("_")
            try:
                path, _ = self.download(
                    self.epaper_fid_url(fid), out_dir, filename=fname, referer=url,
                    progress=(lambda d, t, _l=label: progress(_l, d, t)) if progress else None)
                log(f"  ✓ {label} -> {os.path.basename(path)}")
                results.append({"kind": "epaper", "url": url, "label": label,
                                "path": path, "status": "ok"})
            except Exception as e:  # noqa: BLE001
                log(f"  ✗ {label}: {e}")
                results.append({"kind": "epaper", "url": url, "label": label,
                                "status": "error", "error": str(e)})
        return results

    def _download_ebook(self, url, out_dir, progress, log):
        item = self.get_detail(url)
        try:
            src = self.ebook_pdf_url(url)
        except GdError as e:
            log(f"[e-book] {item.title}: {e}")
            return [{"kind": "ebooks", "title": item.title, "status": "error", "error": str(e)}]
        fname = item.slug()
        try:
            path, _ = self.download(
                src, out_dir, filename=fname, referer=url.rstrip("/") + "/baca",
                progress=(lambda d, t: progress(item.title, d, t)) if progress else None)
            log(f"  ✓ {item.title} -> {os.path.basename(path)}")
            return [{"kind": "ebooks", "title": item.title, "path": path, "status": "ok"}]
        except Exception as e:  # noqa: BLE001
            log(f"  ✗ {item.title}: {e}")
            return [{"kind": "ebooks", "title": item.title, "status": "error", "error": str(e)}]

    def _download_journal(self, url, out_dir, log):
        item = self.get_detail(url)
        try:
            src = self.journal_pdf_url(url)
        except Exception:  # noqa: BLE001
            src = None
        if not src:
            log(f"[jurnal] {item.title}: tidak ada PDF yang bisa diunduh (hanya abstrak).")
            return [{"kind": "journal", "title": item.title, "status": "no-file"}]
        try:
            path, _ = self.download(src, out_dir, filename=item.slug(), referer=url)
            log(f"  ✓ {item.title} -> {os.path.basename(path)}")
            return [{"kind": "journal", "title": item.title, "path": path, "status": "ok"}]
        except Exception as e:  # noqa: BLE001
            log(f"  ✗ {item.title}: {e}")
            return [{"kind": "journal", "title": item.title, "status": "error", "error": str(e)}]


def _dedupe_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{root}_{i}{ext}"):
        i += 1
    return f"{root}_{i}{ext}"


def normalize_url(token: str, kind: str = "repository") -> str:
    """Terima URL penuh atau id/slug; kembalikan URL penuh."""
    token = token.strip()
    if token.startswith(("http://", "https://")):
        return token
    token = token.lstrip("/")
    if token.startswith(("repository/", "ebooks/", "journal/", "catalog/", "epaper/")):
        return f"{BASE}/{token}"
    return f"{BASE}/{kind}/{token}"
