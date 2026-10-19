import os
import json
import logging
import glob
import re
import subprocess
import time
import sys
import shutil
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.rule import Rule
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich import box
from rich.progress import (
    Progress, TextColumn, BarColumn, TaskProgressColumn,
    DownloadColumn, TransferSpeedColumn, TimeRemainingColumn, SpinnerColumn
)
import yt_dlp
from mediadhob.instagram_auth import InstagramAuth
from mediadhob.captions import CaptionEngine
import argparse
from dotenv import set_key
from mediadhob.config import configure_runtime, env_file, write_private_text

class Theme:
    # ── base palette (24-bit truecolor) ──
    BLUE     = "#7aa2f7"
    INDIGO   = "#5d7bf0"
    VIOLET   = "#bb9af7"
    CYAN     = "#7dcfff"
    TEAL     = "#73daca"
    MINT     = "#9ece6a"
    AMBER    = "#e0af68"
    ORANGE   = "#ff9e64"
    ROSE     = "#f7768e"
    FG       = "#c0caf5"
    SOFT     = "#a9b1d6"
    MUTED    = "#565f89"
    FAINT    = "#3b4261"
    BG_CARD  = "#1f2335"

    # ── gradient stops for the wordmark ──
    GRAD = ["#7dcfff", "#7aa2f7", "#bb9af7", "#f7768e"]

    # ── semantic / back-compat aliases (used throughout the app) ──
    ACCENT       = BLUE
    ACCENT2      = CYAN
    GREEN        = MINT
    YELLOW       = AMBER
    RED          = ROSE
    MAGENTA      = VIOLET
    DIM          = MUTED
    WHITE        = FG
    BOLD_WHITE   = "bold #c0caf5"
    SUCCESS      = MINT
    ERROR        = ROSE
    WARN         = AMBER
    INFO         = CYAN
    HIGHLIGHT    = "bold #7aa2f7"
    BORDER_MAIN  = INDIGO
    BORDER_SUB   = FAINT
    BORDER_OK    = TEAL
    BORDER_ERR   = ROSE
    BORDER_WARN  = AMBER
    BORDER_FORGE = VIOLET

T = Theme

# ─── Icons (refined nerd-friendly glyph set) ──────────────────────────────────
class Icon:
    DOWNLOAD  = "⤓"
    YOUTUBE   = "►"
    AUDIO     = "♪"
    REFRESH   = "⟳"
    FORGE     = "✦"
    THUMB     = "▣"
    FOLDER    = "⌂"
    QUIT      = "⏻"
    SUCCESS   = "✔"
    ERROR     = "✘"
    WARN      = "▲"
    INFO      = "ℹ"
    ARROW     = "❯"
    BULLET    = "▪"
    STAR      = "◆"
    CLOCK     = "◴"
    BATCH     = "▦"
    DOT       = "●"
    LINK      = "⛓"
    GEAR      = "⚙"
    SPARK     = "✧"

I = Icon


# ─── Gradient text helper ─────────────────────────────────────────────────────
def _hex_to_rgb(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def gradient_text(text: str, stops=None, bold: bool = False) -> Text:
    """Apply a smooth horizontal multi-stop gradient across a single line."""
    stops = stops or T.GRAD
    rgb_stops = [_hex_to_rgb(s) for s in stops]
    out = Text()
    n = max(len(text) - 1, 1)
    segs = len(rgb_stops) - 1
    for i, ch in enumerate(text):
        f = (i / n) * segs
        idx = min(int(f), segs - 1)
        t = f - idx
        (r1, g1, b1), (r2, g2, b2) = rgb_stops[idx], rgb_stops[idx + 1]
        col = _rgb_to_hex(
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
        out.append(ch, style=f"bold {col}" if bold else col)
    return out

# ─── UI helpers ───────────────────────────────────────────────────────
class UIHelper:
    def __init__(self, console: Console):
        self.console = console

    def rule(self, title: str = "", style: str = T.BORDER_SUB):
        self.console.print(Rule(title, style=style))

    def blank(self):
        self.console.print()

    def print(self, *args, **kwargs):
        self.console.print(*args, **kwargs)

    def panel(self, content, title: str = "", border: str = T.BORDER_MAIN,
              subtitle: str = "", padding=(0, 1), box_style=box.ROUNDED):
        p = Panel(content, title=title, subtitle=subtitle,
                  border_style=border, padding=padding, box=box_style)
        self.console.print(p)

    def _badge_panel(self, glyph: str, color: str, label: str,
                     msg: str, extra_lines: list = None):
        """A modern notification card: colored badge + message body."""
        head = Table.grid(padding=(0, 1))
        head.add_column(width=3, justify="center")
        head.add_column(ratio=1)
        head.add_row(
            Text(f" {glyph} ", style=f"bold {color}"),
            Text(msg, style=T.BOLD_WHITE),
        )
        body = [head]
        for line in (extra_lines or []):
            body.append(Text.from_markup(f"   [{T.MUTED}]{I.BULLET}[/] [{T.SOFT}]{line}[/]"))
        self.console.print(
            Panel(
                Group(*body),
                title=f"[{color}] {label} [/]",
                title_align="left",
                border_style=color,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

    def success(self, msg: str, detail: str = ""):
        extra = [detail] if detail else []
        self._badge_panel(I.SUCCESS, T.SUCCESS, "success", msg, extra)

    def error(self, msg: str, hints: list = None):
        self._badge_panel(I.ERROR, T.ERROR, "error", msg, hints or [])

    def warn(self, msg: str):
        self._badge_panel(I.WARN, T.WARN, "warning", msg)

    def info(self, msg: str):
        self.console.print(f"  [{T.CYAN}]{I.INFO}[/]  [{T.SOFT}]{msg}[/]")

    def status(self, msg: str, spinner: str = "dots"):
        return self.console.status(
            f"[{T.ACCENT}]{msg}[/]", spinner=spinner,
            spinner_style=T.CYAN
        )

    def ask(self, prompt: str, **kwargs) -> str:
        label = f"[{T.VIOLET}]{I.ARROW}[/] [{T.WHITE}]{prompt}[/]"
        return Prompt.ask(label, **kwargs)

    def ask_choice(self, prompt: str, choices: list, default: str = None) -> str:
        chips = Text("  ")
        for c in choices:
            if c == (default or choices[0]):
                chips.append(f" {c} ", style=f"bold #1f2335 on {T.BLUE}")
            else:
                chips.append(f" {c} ", style=f"{T.SOFT} on {T.FAINT}")
            chips.append(" ")
        self.console.print(chips)
        label = f"[{T.VIOLET}]{I.ARROW}[/] [{T.WHITE}]{prompt}[/]"
        return Prompt.ask(label, choices=choices, default=default or choices[0])


# ══════════════════════════════════════════════════════════════════════════════
#  BANNER & CHROME
# ══════════════════════════════════════════════════════════════════════════════

BANNER_ART = r"""
  ███╗   ███╗███████╗██████╗ ██╗ █████╗ ██████╗ ██╗  ██╗ ██████╗ ██████╗
  ████╗ ████║██╔════╝██╔══██╗██║██╔══██╗██╔══██╗██║  ██║██╔═══██╗██╔══██╗
  ██╔████╔██║█████╗  ██║  ██║██║███████║██║  ██║███████║██║   ██║██████╔╝
  ██║╚██╔╝██║██╔══╝  ██║  ██║██║██╔══██║██║  ██║██╔══██║██║   ██║██╔══██╗
  ██║ ╚═╝ ██║███████╗██████╔╝██║██║  ██║██████╔╝██║  ██║╚██████╔╝██████╔╝
  ╚═╝     ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═════╝"""

TAGLINE = "professional media toolkit  ·  instagram & youtube"


def render_banner(ui: UIHelper):
    """Render the gradient wordmark with a tagline — shown once per session."""
    lines = [ln for ln in BANNER_ART.split("\n") if ln.strip("\n")]
    grad = Group(*[gradient_text(ln, T.GRAD, bold=True) for ln in lines if ln])
    ui.console.print(grad)
    tag = Text()
    tag.append("   ", style=T.MUTED)
    tag.append(f"{I.SPARK} ", style=T.VIOLET)
    tag.append(TAGLINE, style=f"italic {T.MUTED}")
    ui.console.print(tag)
    ui.blank()


def render_statusbar(ui: UIHelper, save_dir: str, files_count: int):
    """Slim dashboard status bar: brand · location · session stats."""
    now = datetime.now().strftime("%H:%M:%S")

    brand = Text()
    brand.append(f" {I.STAR} ", style=f"bold {T.BLUE}")
    brand.append("MEDIADHOB", style=f"bold {T.FG}")
    brand.append("  v0.2.0", style=T.MUTED)

    loc = Text()
    loc.append(f"{I.FOLDER} ", style=T.VIOLET)
    short = save_dir if len(save_dir) <= 38 else "…" + save_dir[-37:]
    loc.append(short, style=T.SOFT)

    stats = Text()
    stats.append(f"{I.DOWNLOAD} ", style=T.TEAL)
    stats.append(f"{files_count}", style=f"bold {T.TEAL}")
    stats.append(" saved   ", style=T.MUTED)
    stats.append(f"{I.CLOCK} ", style=T.AMBER)
    stats.append(now, style=T.SOFT)
    stats.append(" ", style=T.MUTED)

    bar = Table.grid(expand=True)
    bar.add_column(justify="left", ratio=1)
    bar.add_column(justify="center", ratio=1)
    bar.add_column(justify="right", ratio=1)
    bar.add_row(brand, loc, stats)

    ui.console.print(
        Panel(bar, border_style=T.BORDER_MAIN, box=box.ROUNDED, padding=(0, 1))
    )


def render_header(ui: UIHelper, save_dir: str, files_count: int):
    """Backward-compatible full header (banner + status bar)."""
    render_banner(ui)
    render_statusbar(ui, save_dir, files_count)


def render_menu(ui: UIHelper):
    ui.blank()
    # category -> list of (key, icon, label, key_color, hint)
    groups = [
        ("download", T.BLUE, [
            ("1", I.DOWNLOAD, "Instagram video",   "media + audio"),
            ("2", I.YOUTUBE,  "YouTube video",      "full or audio-only"),
            ("3", I.YOUTUBE,  "YouTube segment",    "trim by timestamps"),
            ("4", I.BATCH,    "Batch download",     "urls from a file"),
            ("8", I.THUMB,    "YouTube thumbnail",  "maxres + fallback"),
        ]),
        ("studio", T.VIOLET, [
            ("7", I.FORGE,    "ClipForge",          "cut + subtitle extract"),
        ]),
        ("system", T.AMBER, [
            ("5", I.REFRESH,  "Refresh IG cookies", "auto login / manual"),
            ("6", I.FOLDER,   "Change save dir",    "migrate metadata"),
            ("q", I.QUIT,     "Quit",               "end session"),
        ]),
    ]

    blocks = []
    for cat_name, cat_color, entries in groups:
        header = Text()
        header.append("┃ ", style=cat_color)
        header.append(cat_name.upper(), style=f"bold {cat_color}")
        blocks.append(header)

        tbl = Table.grid(padding=(0, 2))
        tbl.add_column(width=4, justify="right")
        tbl.add_column(width=2, justify="center")
        tbl.add_column(width=20, no_wrap=True)
        tbl.add_column(overflow="ellipsis")
        for key_, icon, label, hint in entries:
            key_color = T.ROSE if key_ == "q" else cat_color
            tbl.add_row(
                Text(f"[{key_}]", style=f"bold {key_color}"),
                Text(icon, style=cat_color),
                Text(label, style=T.FG),
                Text(hint, style=T.MUTED),
            )
        blocks.append(tbl)
        blocks.append(Text(""))  # spacer

    ui.console.print(
        Panel(
            Group(*blocks[:-1]),
            title=f"[{T.SOFT}] {I.GEAR} command center [/]",
            title_align="left",
            border_style=T.BORDER_SUB,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def render_download_submenu(ui: UIHelper) -> str | None:
    ui.blank()
    options = [
        ("1", I.DOWNLOAD, "video + audio", T.TEAL,  "best quality, merged mp4"),
        ("2", I.YOUTUBE,  "video only",    T.BLUE,  "no audio track"),
        ("3", I.AUDIO,    "audio only",    T.AMBER, "extracted m4a"),
        ("q", I.QUIT,     "cancel",        T.ROSE,  ""),
    ]
    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(width=4, justify="right")
    tbl.add_column(width=2, justify="center")
    tbl.add_column(width=16, no_wrap=True)
    tbl.add_column(overflow="ellipsis")
    for k, icon, label, color, hint in options:
        tbl.add_row(
            Text(f"[{k}]", style=f"bold {color}"),
            Text(icon, style=color),
            Text(label, style=T.FG),
            Text(hint, style=T.MUTED),
        )
    ui.console.print(
        Panel(
            tbl,
            title=f"[{T.SOFT}] {I.SPARK} output format [/]",
            title_align="left",
            border_style=T.BORDER_SUB,
            box=box.ROUNDED,
            padding=(0, 2),
        )
    )
    choice = ui.ask_choice("select format", ["1", "2", "3", "q"], default="1")
    return {"1": "video+audio", "2": "video_only", "3": "audio_only", "q": None}[choice]


# ══════════════════════════════════════════════════════════════════════════════
#  CORE DOWNLOADER ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class MediaDownloader:
    def __init__(self, console: Console, ui: UIHelper,
                 cookies_file="cookies.txt", username=None,
                 password=None, save_dir=None):
        self.console       = console
        self.ui            = ui
        self.cookies_file  = cookies_file
        self.username      = username
        self.password      = password
        self.save_dir      = save_dir or os.environ.get('SAVE_PATH', 'downloaded_media')
        self.metadata_file = os.path.join(self.save_dir, 'metadata.json')
        self.proxy_list    = self._load_proxies()
        self._validate_save_dir()

        # Initialize Instagram Private API auth
        self._ig_auth = None
        if self.username and self.password:
            try:
                self._ig_auth = InstagramAuth(
                    username=self.username,
                    password=self.password,
                    cookies_file=self.cookies_file,
                    session_file=os.path.join(
                        os.path.dirname(self.cookies_file) or '.', 'ig_session.json'
                    ),
                    ui=self.ui,
                )
            except ImportError:
                logging.warning("instagrapi not installed — Instagram auth disabled")

    # ── Directory helpers ─────────────────────────────────────────────────────

    def _load_proxies(self) -> list:
        return []

    def _validate_save_dir(self):
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            if not os.access(self.save_dir, os.W_OK):
                raise PermissionError(f"no write permission for {self.save_dir}")
            logging.info(f"save dir validated: {self.save_dir}")
        except Exception as e:
            logging.error(f"save dir error: {e}")
            raise ValueError(f"invalid save directory '{self.save_dir}': {e}")

    def set_save_dir(self, new_path: str):
        old_meta = self.metadata_file
        self.save_dir      = new_path
        self.metadata_file = os.path.join(self.save_dir, 'metadata.json')
        self._validate_save_dir()
        if os.path.exists(old_meta) and old_meta != self.metadata_file:
            try:
                os.rename(old_meta, self.metadata_file)
                self.ui.info(f"metadata migrated → {self.metadata_file}")
            except Exception as e:
                self.ui.warn(f"could not migrate metadata: {e}")
        self.ui.success(f"save directory → {self.save_dir}")
        logging.info(f"save dir set: {self.save_dir}")

    # ── Metadata ──────────────────────────────────────────────────────────────

    def save_metadata(self, metadata: dict):
        try:
            existing = []
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    try:
                        existing = json.load(f)
                        if not isinstance(existing, list):
                            existing = []
                    except json.JSONDecodeError:
                        existing = []
            existing.append(metadata)
            os.makedirs(os.path.dirname(self.metadata_file), exist_ok=True)
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            logging.info(f"metadata saved to {self.metadata_file}")
        except Exception as e:
            logging.error(f"metadata save failed: {e}")
            self.ui.warn(f"could not save metadata: {e}")

    # ── Instagram cookies (via Private API — no browser needed) ────────────────

    def refresh_instagram_cookies(self):
        """
        تحديث كوكيز Instagram باستخدام Private API (instagrapi).
        لا يحتاج متصفح — يتصل مباشرة بـ Instagram API.
        """
        if not self._ig_auth:
            if not (self.username and self.password):
                raise ValueError("INSTA_USER / INSTA_PASS not set in .env")
            self._ig_auth = InstagramAuth(
                username=self.username,
                password=self.password,
                cookies_file=self.cookies_file,
                session_file=os.path.join(os.path.dirname(self.cookies_file) or '.', 'ig_session.json'),
                ui=self.ui,
            )

        success = self._ig_auth.force_refresh()
        if success:
            info = self._ig_auth.get_session_info()
            self.ui.success(
                "instagram cookies refreshed (Private API)",
                f"saved {info.get('cookie_count', '?')} cookies "
                f"| sessionid: {'found' if info.get('has_sessionid') else 'MISSING'}"
            )
        else:
            raise Exception(
                "instagram authentication failed — "
                "check INSTA_USER / INSTA_PASS in .env"
            )
        return success

    def refresh_instagram_cookies_manual(self, session_id: str):
        """
        تحديث كوكيز Instagram يدوياً — يلصق المستخدم sessionid من المتصفح.
        """
        session_id = session_id.strip()
        if not session_id:
            raise ValueError("sessionid is empty")
        if any(char.isspace() for char in session_id):
            raise ValueError("sessionid must not contain whitespace")

        from datetime import timedelta
        expiry = str(int((datetime.now() + timedelta(days=365)).timestamp()))

        lines = [
            "# Netscape HTTP Cookie File",
            "# Generated by MEDIADHOB (manual paste)",
            f"# Date: {datetime.now().isoformat()}",
            "",
            f".instagram.com\tTRUE\t/\tTRUE\t{expiry}\tsessionid\t{session_id}",
            f".instagram.com\tTRUE\t/\tTRUE\t{expiry}\tds_user_id\t{session_id.split('%3A')[0] if '%3A' in session_id else ''}",
        ]

        write_private_text(self.cookies_file, '\n'.join(lines) + '\n')

        self.ui.success(
            "cookies saved (manual)",
            f"sessionid written to {self.cookies_file}"
        )
        return True

    def download_youtube(self, video_url: str, download_type="video+audio",
                         start_time=None, end_time=None):
        try:
            yt_dir = os.path.join(self.save_dir, 'YouTube')
            os.makedirs(yt_dir, exist_ok=True)

            if start_time and end_time:
                out_dir = os.path.join(yt_dir, 'Clips')
                outtmpl = os.path.join(out_dir, 'temp_youtube_%(id)s_segment.%(ext)s')
            else:
                out_dir = os.path.join(yt_dir, 'Videos')
                outtmpl = os.path.join(out_dir, 'youtube_%(id)s.%(ext)s')
            os.makedirs(out_dir, exist_ok=True)

            base_opts = dict(quiet=True, noprogress=True, no_warnings=True,
                             ignoreerrors=False, retries=3, fragment_retries=3)

            if download_type == "video+audio":
                ydl_opts = {**base_opts, 'outtmpl': outtmpl,
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}]}
            elif download_type == "video_only":
                ydl_opts = {**base_opts, 'outtmpl': outtmpl,
                    'format': 'bestvideo[ext=mp4]/bestvideo/best[ext=mp4]/best'}
            elif download_type == "audio_only":
                ydl_opts = {**base_opts, 'outtmpl': outtmpl,
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'}]}
            else:
                raise ValueError(f"invalid download type: {download_type}")

            spinner = "earth"
            lbl = f"downloading youtube [{download_type}] …"
            with self.ui.status(lbl, spinner):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info     = ydl.extract_info(video_url, download=True)
                        filename = ydl.prepare_filename(info)

                        if not os.path.exists(filename):
                            vid_id = info.get('id', '')
                            found  = glob.glob(os.path.join(os.path.dirname(filename), f'*{vid_id}*'))
                            if found:
                                filename = found[0]
                            else:
                                return {"status": "failed", "error": "file not found after download"}

                        if start_time and end_time:
                            clips_dir = os.path.join(yt_dir, 'Clips')
                            ext = os.path.splitext(filename)[1]
                            trimmed = os.path.join(clips_dir, f'youtube_{info.get("id","")}_segment{ext}')
                            cmd = ['ffmpeg', '-y', '-i', filename,
                                   '-ss', start_time, '-to', end_time,
                                   '-c:v', 'copy', '-c:a', 'copy', trimmed]
                            try:
                                subprocess.run(cmd, check=True, capture_output=True, text=True)
                                try:
                                    os.remove(filename)
                                except Exception:
                                    pass
                                filename = trimmed
                            except subprocess.CalledProcessError as e:
                                return {"status": "failed", "error": f"ffmpeg trim failed: {e.stderr[:200]}"}

                        meta = {
                            "platform": "youtube", "post_id": info.get("id", ""),
                            "filename": filename, "download_type": download_type,
                            "timestamp": datetime.now().isoformat(),
                            "post_url": video_url, "title": info.get("title", ""),
                            "start_time": start_time or "", "end_time": end_time or "",
                        }
                        self.save_metadata(meta)
                        return {"status": "success", "filename": filename, "metadata": meta}

                    except yt_dlp.utils.DownloadError as e:
                        err = str(e)
                        if "Requested format is not available" in err:
                            self.ui.info("retrying with fallback format …")
                            ydl_opts['format'] = 'best'
                            try:
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                                    info     = ydl2.extract_info(video_url, download=True)
                                    filename = ydl2.prepare_filename(info)
                                    if not os.path.exists(filename):
                                        vid_id = info.get('id', '')
                                        found  = glob.glob(os.path.join(os.path.dirname(filename), f'*{vid_id}*'))
                                        if found:
                                            filename = found[0]
                                    meta = {
                                        "platform": "youtube", "post_id": info.get("id", ""),
                                        "filename": filename, "download_type": "best_available",
                                        "timestamp": datetime.now().isoformat(),
                                        "post_url": video_url, "title": info.get("title", ""),
                                    }
                                    self.save_metadata(meta)
                                    return {"status": "success", "filename": filename, "metadata": meta}
                            except Exception as e2:
                                return {"status": "failed", "error": str(e2)}
                        return {"status": "failed", "error": err}

        except Exception as e:
            logging.error(f"youtube download error: {e}")
            return {"status": "failed", "error": str(e)}

    # ── Instagram download ────────────────────────────────────────────────────

    def download_instagram(self, post_url: str, download_type="video+audio"):
        try:
            ig_dir = os.path.join(self.save_dir, 'Instagram')
            os.makedirs(ig_dir, exist_ok=True)

            # Auto-authenticate if no cookies exist
            if not os.path.exists(self.cookies_file):
                if self._ig_auth:
                    self.ui.info("no cookies found — authenticating via Private API …")
                    if not self._ig_auth.login():
                        return {"status": "failed",
                                "error": "authentication failed — use option [5]"}
                else:
                    return {"status": "failed",
                            "error": "cookies.txt not found — use option [5] to refresh cookies first"}

            fmt_map = {
                "video+audio": ('bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                                'mp4', 'insta_%(id)s.%(ext)s'),
                "video_only":  ('bestvideo[ext=mp4]', None, 'insta_%(id)s_video.%(ext)s'),
                "audio_only":  ('bestaudio[ext=m4a]', None, 'insta_%(id)s_audio.%(ext)s'),
            }
            if download_type not in fmt_map:
                raise ValueError(f"invalid type: {download_type}")

            fmt, merge, tmpl = fmt_map[download_type]
            ydl_opts = dict(
                outtmpl=os.path.join(ig_dir, tmpl),
                format=fmt, cookiefile=self.cookies_file,
                quiet=True, retries=3, fragment_retries=3,
                noprogress=True, no_warnings=True, ignoreerrors=False,
            )
            if merge:
                ydl_opts['merge_output_format'] = merge

            with self.ui.status(f"downloading instagram [{download_type}] …", "earth"):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info     = ydl.extract_info(post_url, download=True)
                        filename = ydl.prepare_filename(info)
                        meta = {
                            "platform": "instagram", "post_id": info.get("id", ""),
                            "filename": filename, "download_type": download_type,
                            "timestamp": datetime.now().isoformat(),
                            "post_url": post_url, "title": info.get("title", ""),
                        }
                        self.save_metadata(meta)
                        return {"status": "success", "filename": filename, "metadata": meta}
                    except yt_dlp.utils.DownloadError as e:
                        err = str(e).lower()
                        if ("login required" in err or "private" in err) and self._ig_auth:
                            # Auto-retry: refresh cookies and try again
                            self.ui.warn("cookies expired — auto-refreshing …")
                            if self._ig_auth.force_refresh():
                                self.ui.info("retrying download with fresh cookies …")
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                                    info2     = ydl2.extract_info(post_url, download=True)
                                    filename2 = ydl2.prepare_filename(info2)
                                    meta2 = {
                                        "platform": "instagram", "post_id": info2.get("id", ""),
                                        "filename": filename2, "download_type": download_type,
                                        "timestamp": datetime.now().isoformat(),
                                        "post_url": post_url, "title": info2.get("title", ""),
                                    }
                                    self.save_metadata(meta2)
                                    return {"status": "success", "filename": filename2, "metadata": meta2}
                        if "login required" in err or "private" in err:
                            msg = "instagram requires login or cookies are expired — use option [5]"
                        else:
                            msg = f"instagram download failed: {e}"
                        logging.error(msg)
                        return {"status": "failed", "error": msg}

        except Exception as e:
            logging.error(f"instagram download error: {e}")
            return {"status": "failed", "error": str(e)}

    # ── Thumbnail download ────────────────────────────────────────────────────

    def download_youtube_thumbnail(self, video_url: str):
        try:
            parsed = urlparse(video_url)
            if parsed.hostname in ['www.youtube.com', 'youtube.com']:
                vid_id = parse_qs(parsed.query).get('v', [None])[0]
            elif parsed.hostname == 'youtu.be':
                vid_id = parsed.path[1:]
            else:
                raise ValueError("invalid youtube url")

            if not vid_id:
                raise ValueError("could not extract video id")

            qualities = ['maxresdefault', 'sddefault', 'hqdefault', 'mqdefault', 'default']
            thumb_url = None
            for q in qualities:
                url = f"https://img.youtube.com/vi/{vid_id}/{q}.jpg"
                if requests.head(url, timeout=10).status_code == 200:
                    thumb_url = url
                    self.ui.info(f"found thumbnail quality: {q}")
                    break

            if not thumb_url:
                raise Exception("no thumbnail found for this video")

            out_dir  = os.path.join(self.save_dir, 'YouTube', 'Thumbnails')
            os.makedirs(out_dir, exist_ok=True)
            filename = os.path.join(out_dir, f'youtube_{vid_id}_thumbnail.jpg')

            with requests.get(thumb_url, timeout=10, stream=True) as r:
                r.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            meta = {
                "platform": "youtube_thumbnail", "post_id": vid_id,
                "filename": filename, "timestamp": datetime.now().isoformat(),
                "post_url": video_url,
            }
            self.save_metadata(meta)
            logging.info(f"thumbnail saved → {filename}")
            return {"status": "success", "filename": filename, "metadata": meta}

        except requests.RequestException as e:
            return {"status": "failed", "error": f"network error: {e}"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ── ClipForge ─────────────────────────────────────────────────────────────

    def run_clipforge_process(self, video_path: str, original_url: str):
        if not os.path.exists(video_path):
            self.ui.error(f"video file not found: {video_path}")
            return

        self.ui.panel(
            f"[{T.MAGENTA}]{I.FORGE}  ClipForge activated[/]\n"
            f"[{T.DIM}]source: {video_path}[/]",
            title=f"[{T.MAGENTA}] clipforge [/]",
            border=T.BORDER_FORGE,
        )

        try:
            self.ui.info("fetching arabic auto-subtitles …")
            tmp = os.path.join(self.save_dir,
                               f"tmp_subs_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            cmd = f'yt-dlp --write-auto-subs --sub-lang ar --skip-download "{original_url}" -o "{tmp}"'
            subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)

            vtt_files = glob.glob(f'{tmp}.ar.vtt')
            if vtt_files:
                script_path = os.path.join(self.save_dir, "clean_script.txt")
                with open(vtt_files[0], 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                clean = [re.sub(r'<[^>]+>', '', l).strip()
                         for l in lines
                         if '-->' not in l and 'WEBVTT' not in l
                         and l.strip() and not l.strip().isdigit()]
                with open(script_path, 'w', encoding='utf-8') as f:
                    f.write(' '.join(clean))
                self.ui.success(f"clean script → {script_path}")
                try:
                    os.remove(vtt_files[0])
                except Exception:
                    pass
            else:
                self.ui.warn("no arabic subtitles found — analyze video manually")

        except subprocess.CalledProcessError as e:
            self.ui.warn(f"subtitle fetch failed: {e.stderr[:100] if e.stderr else 'unknown'}")
        except Exception as e:
            self.ui.warn(f"subtitle processing error: {e}")

        try:
            n_str = self.ui.ask("how many clips to forge", default="1")
            n     = int(n_str)
            if n <= 0:
                self.ui.error("number must be positive"); return

            ok_count = fail_count = 0

            for i in range(1, n + 1):
                self.ui.rule(f"  clip {i} / {n}  ", style=T.MAGENTA)

                start = self.ui.ask(f"start time for clip {i} (HH:MM:SS)")
                if not re.match(r"^\d{2}:\d{2}:\d{2}$", start):
                    self.ui.warn("invalid time format — skipping"); fail_count += 1; continue

                end = self.ui.ask(f"end time for clip {i} (HH:MM:SS)")
                if not re.match(r"^\d{2}:\d{2}:\d{2}$", end):
                    self.ui.warn("invalid time format — skipping"); fail_count += 1; continue

                base = os.path.splitext(os.path.basename(video_path))[0]
                out  = os.path.join(self.save_dir, f"forged_clip_{i}_{base}.mp4")
                cmd2 = ['ffmpeg', '-y', '-i', video_path,
                        '-ss', start, '-to', end,
                        '-c:v', 'libx264', '-preset', 'veryslow', '-crf', '17',
                        '-c:a', 'aac', '-b:a', '320k', out]

                with self.ui.status(f"forging clip {i} with ffmpeg …", "moon"):
                    try:
                        subprocess.run(cmd2, check=True, capture_output=True, text=True)
                        self.ui.success(f"clip {i} saved → {out}")
                        ok_count += 1
                    except subprocess.CalledProcessError as e:
                        self.ui.error(f"ffmpeg failed for clip {i}",
                                      hints=[e.stderr[:200] if e.stderr else "unknown error"])
                        fail_count += 1

            self.ui.blank()
            self.ui.panel(
                f"[{T.SUCCESS}]{I.SUCCESS}  successful  {ok_count}[/]\n"
                f"[{T.ERROR}]{I.ERROR}  failed      {fail_count}[/]\n"
                f"[{T.DIM}]{I.INFO}  total       {ok_count + fail_count}[/]",
                title=f"[{T.MAGENTA}] clipforge summary [/]",
                border=T.BORDER_FORGE,
            )

        except ValueError:
            self.ui.error("invalid number entered")
        except Exception as e:
            self.ui.error(f"unexpected clipforge error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  APP UI
# ══════════════════════════════════════════════════════════════════════════════

class AppUI:
    def __init__(self, save_dir=None):
        self.console  = Console()
        self.ui       = UIHelper(self.console)
        self.username = os.environ.get('INSTA_USER')
        self.password = os.environ.get('INSTA_PASS')
        self.save_dir = save_dir or os.environ.get('SAVE_PATH', 'downloaded_media')
        self.files_downloaded = 0
        self.session_start    = datetime.now()

        if not (self.username and self.password):
            self.ui.warn(
                "INSTA_USER / INSTA_PASS not found in environment\n"
                f"  [{T.DIM}]instagram features will require manual cookie setup[/]"
            )

        self.downloader = MediaDownloader(
            self.console, self.ui,
            username=self.username,
            password=self.password,
            save_dir=self.save_dir,
        )

    # ── Persist SAVE_PATH in .env so it survives restarts ──────────────────

    def _persist_save_path(self, new_path: str):
        """Persist the save path in the launch directory, not site-packages."""
        set_key(str(env_file()), "SAVE_PATH", new_path, quote_mode="always")
        logging.info("SAVE_PATH updated in local .env")

    def _validate_time(self, t: str) -> bool:
        m = re.match(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?$', t)
        if not m:
            return False
        h = int(m.group(1)); mins = int(m.group(2)); s = int(m.group(3) or 0)
        return h <= 23 and mins <= 59 and s <= 59

    # ── Caption helpers ─────────────────────────────────────────────────────

    def _ask_captions(self) -> tuple[bool, str]:
        """Ask user if they want captions. Returns (want_captions, language)."""
        choice = self.ui.ask_choice("add captions?", ["y", "n"], default="n")
        if choice != "y":
            return False, ""
        lang = self.ui.ask_choice("caption language", ["ar", "en", "auto"], default="ar")
        return True, lang

    def _apply_captions(self, result: dict, video_url: str, language: str):
        """Apply captions to a successfully downloaded video."""
        if not result or result.get("status") != "success":
            return

        video_path = result.get("filename", "")
        if not video_path or not os.path.exists(video_path):
            return

        engine = CaptionEngine(ui=self.ui)
        captioned = engine.add_captions(
            video_path=video_path,
            video_url=video_url,
            language=language,
            burn=True,
        )
        if captioned:
            result["filename"] = captioned
            result["captioned"] = True

    # ── Result display ────────────────────────────────────────────────────

    def _show_result(self, result: dict, extra: str = ""):
        if result and result.get("status") == "success":
            fn = result.get('filename', '')
            detail = f"saved → {fn}"
            if result.get("captioned"):
                detail += f"\n   {I.SUCCESS} captions embedded"
            if extra:
                detail += f"\n   {extra}"
            self.ui.success("download complete", detail)
            self.files_downloaded += 1
        else:
            err = result.get('error', 'unknown error') if result else 'unknown'
            self.ui.error(
                "download failed",
                hints=[err,
                       "check internet connection",
                       "verify the url",
                       "try refreshing cookies (for instagram)"]
            )

    def handle_instagram(self):
        url = self.ui.ask("instagram video url")
        if url.lower() == 'q' or not url.strip():
            return
        dt = render_download_submenu(self.ui)
        if not dt:
            return
        want_caps, lang = self._ask_captions()
        result = self.downloader.download_instagram(url, download_type=dt)
        if want_caps and result and result.get("status") == "success":
            self._apply_captions(result, url, lang)
        self._show_result(result)

    def handle_youtube(self):
        url = self.ui.ask("youtube video url")
        if url.lower() == 'q' or not url.strip():
            return
        dt = render_download_submenu(self.ui)
        if not dt:
            return
        want_caps, lang = self._ask_captions()
        result = self.downloader.download_youtube(url, download_type=dt)
        if want_caps and result and result.get("status") == "success":
            self._apply_captions(result, url, lang)
        self._show_result(result)

    def handle_youtube_segment(self):
        url = self.ui.ask("youtube video url")
        if url.lower() == 'q' or not url.strip():
            return
        start = self.ui.ask("start time (HH:MM:SS or MM:SS)")
        if not self._validate_time(start):
            self.ui.error("invalid start time format"); return
        end = self.ui.ask("end time (HH:MM:SS or MM:SS)")
        if not self._validate_time(end):
            self.ui.error("invalid end time format"); return
        dt = render_download_submenu(self.ui)
        if not dt:
            return
        want_caps, lang = self._ask_captions()
        result = self.downloader.download_youtube(
            url, download_type=dt, start_time=start, end_time=end
        )
        if want_caps and result and result.get("status") == "success":
            self._apply_captions(result, url, lang)
        self._show_result(result, extra=f"segment  {start}  →  {end}")

    def handle_batch(self):
        self.ui.blank()

        # ── اختيار طريقة إدخال الروابط ──
        options = [
            ("1", I.LINK,  "Paste urls (open editor)", T.BLUE,   "notepad opens, paste & save"),
            ("2", I.BATCH, "Load from file",           T.AMBER,  "path to a text file"),
            ("q", I.QUIT,  "Cancel",                   T.ROSE,   ""),
        ]
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column(width=4, justify="right")
        tbl.add_column(width=2, justify="center")
        tbl.add_column(width=24, no_wrap=True)
        tbl.add_column(overflow="ellipsis")
        for k, icon, label, color, hint in options:
            tbl.add_row(
                Text(f"[{k}]", style=f"bold {color}"),
                Text(icon, style=color),
                Text(label, style=T.FG),
                Text(hint, style=T.MUTED),
            )
        self.ui.console.print(
            Panel(
                tbl,
                title=f"[{T.SOFT}] {I.BATCH} batch input [/]",
                title_align="left",
                border_style=T.BORDER_SUB,
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )
        method = self.ui.ask_choice("select method", ["1", "2", "q"], default="1")
        if method == "q":
            return

        urls = []

        if method == "1":
            # ── فتح محرر نصوص مؤقت ──
            import tempfile
            tmp_path = os.path.join(tempfile.gettempdir(), "mediadhob_batch_urls.txt")
            # كتابة ملف مبدئي مع تعليمات
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write("# Paste your URLs below (one per line)\n")
                f.write("# Lines starting with # are ignored\n")
                f.write("# Save and close the editor when done\n\n")

            self.ui.info("opening editor — paste your urls, save, then close …")

            # تحديد المحرر المناسب حسب النظام
            if sys.platform == "win32":
                editor = os.environ.get("EDITOR", "notepad")
            else:
                editor = os.environ.get("EDITOR", "nano")

            try:
                subprocess.run([editor, tmp_path], check=True)
            except FileNotFoundError:
                # fallback to notepad on Windows
                try:
                    subprocess.run(["notepad", tmp_path], check=True)
                except Exception as e:
                    self.ui.error(f"could not open editor: {e}")
                    return
            except Exception as e:
                self.ui.error(f"editor error: {e}")
                return

            # قراءة الروابط بعد إغلاق المحرر
            if not os.path.exists(tmp_path):
                self.ui.error("temp file not found after editor closed")
                return

            with open(tmp_path, 'r', encoding='utf-8') as f:
                urls = [l.strip() for l in f if l.strip() and not l.startswith('#')]

            # تنظيف الملف المؤقت
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        else:
            # ── تحميل من ملف جاهز ──
            path = self.ui.ask("path to urls file", default="urls.txt")
            if path.lower() == 'q':
                return
            if not os.path.exists(path):
                self.ui.error(f"file not found: {path}")
                return
            with open(path, 'r', encoding='utf-8') as f:
                urls = [l.strip() for l in f if l.strip() and not l.startswith('#')]

        if not urls:
            self.ui.error("no valid urls found")
            return

        self.ui.info(f"found {len(urls)} url(s)")
        self.ui.blank()

        dt = render_download_submenu(self.ui)
        if not dt:
            return

        self.ui.info(f"starting batch download [{dt}] …")
        ok = fail = 0

        with Progress(
            SpinnerColumn(style=T.ACCENT),
            TextColumn(f"[{T.DIM}]{{task.description}}"),
            BarColumn(complete_style=T.SUCCESS, finished_style=T.SUCCESS),
            TaskProgressColumn(),
            console=self.console,
        ) as prog:
            task = prog.add_task("batch", total=len(urls))
            for i, url in enumerate(urls, 1):
                prog.update(task, description=f"[{i}/{len(urls)}] {url[:50]}")
                if "instagram.com" in url:
                    r = self.downloader.download_instagram(url, dt)
                elif "youtube.com" in url or "youtu.be" in url:
                    r = self.downloader.download_youtube(url, dt)
                else:
                    self.ui.warn(f"unsupported url — skipping: {url[:60]}")
                    prog.advance(task); continue

                if r and r.get("status") == "success":
                    ok += 1; self.files_downloaded += 1
                else:
                    fail += 1
                prog.advance(task)

        self.ui.panel(
            f"[{T.SUCCESS}]{I.SUCCESS}  ok      {ok}[/]\n"
            f"[{T.ERROR}]{I.ERROR}  failed  {fail}[/]\n"
            f"[{T.DIM}]{I.INFO}  total   {len(urls)}[/]",
            title=f"[{T.ACCENT}] batch summary [/]",
            border=T.BORDER_MAIN,
        )

    def handle_cookies_refresh(self):
        self.ui.blank()

        options = [
            ("1", "Auto login (Private API)",
             T.ACCENT, "uses INSTA_USER / INSTA_PASS from .env"),
            ("2", "Paste sessionid manually",
             T.YELLOW, "copy from browser DevTools"),
            ("q", "Cancel",
             T.ERROR, ""),
        ]
        table = Table.grid(padding=(0, 2))
        table.add_column(width=3, justify="right")
        table.add_column(width=28, no_wrap=True)
        table.add_column()
        for key, label, color, hint in options:
            table.add_row(
                Text(key,   style=f"bold {color}"),
                Text(label, style=T.WHITE),
                Text(f"\u2014 {hint}" if hint else "", style=T.DIM),
            )
        self.ui.panel(table, title=f"[{T.DIM}] cookie method [/]",
                      border=T.BORDER_SUB, padding=(0, 2))

        choice = self.ui.ask_choice("select method", ["1", "2", "q"], default="1")
        if choice == "q":
            return

        if choice == "1":
            # Auto login via Private API
            try:
                self.downloader.refresh_instagram_cookies()
            except Exception as e:
                self.ui.error("auto login failed",
                              hints=[str(e),
                                     "check INSTA_USER / INSTA_PASS in .env",
                                     "try option [2] to paste sessionid manually"])
        else:
            # Manual sessionid paste
            self.ui.blank()
            self.ui.info("how to get sessionid:")
            self.ui.panel(
                Text.from_markup(
                    f"[{T.WHITE}]1.[/] Open [{T.ACCENT}]instagram.com[/] in Chrome/Edge and log in\n"
                    f"[{T.WHITE}]2.[/] Press [{T.ACCENT}]F12[/] to open DevTools\n"
                    f"[{T.WHITE}]3.[/] Go to [{T.ACCENT}]Application[/] tab > [{T.ACCENT}]Cookies[/] > [{T.ACCENT}]instagram.com[/]\n"
                    f"[{T.WHITE}]4.[/] Find [{T.SUCCESS}]sessionid[/] and copy its [{T.SUCCESS}]Value[/]"
                ),
                title=f"[{T.DIM}] instructions [/]",
                border=T.BORDER_SUB, padding=(1, 2),
            )
            sid = self.ui.ask("paste sessionid value here", password=True)
            if not sid or sid.lower() == 'q':
                return
            try:
                self.downloader.refresh_instagram_cookies_manual(sid)
            except Exception as e:
                self.ui.error("manual cookie setup failed", hints=[str(e)])

    def handle_change_dir(self):
        new = self.ui.ask("new save directory", default=self.downloader.save_dir)
        if new.lower() == 'q':
            return
        try:
            self.downloader.set_save_dir(new)
            self._persist_save_path(new)
            self.ui.info("path saved permanently — will be used on next launch")
        except Exception as e:
            self.ui.error(f"failed to set directory: {e}")

    def handle_clipforge(self):
        self.ui.blank()
        self.ui.panel(
            f"[{T.MAGENTA}]{I.FORGE}  ClipForge — precision video cutting + subtitle extraction[/]",
            title=f"[{T.MAGENTA}] clipforge [/]",
            border=T.BORDER_FORGE,
        )

        yt_url = self.ui.ask("youtube video url")
        if yt_url.lower() == 'q' or not yt_url.strip():
            return

        try:
            n = int(self.ui.ask("how many clips to forge", default="1"))
            if n <= 0:
                self.ui.error("number must be positive"); return
        except ValueError:
            self.ui.error("invalid number"); return

        dt = render_download_submenu(self.ui)
        if not dt:
            return

        ok_count = fail_count = 0

        for i in range(1, n + 1):
            self.ui.rule(f"  clip {i} / {n}  ", style=T.MAGENTA)

            start = self.ui.ask(f"start time for clip {i} (HH:MM:SS or MM:SS)")
            if start.lower() == 'q':
                break
            if not self._validate_time(start):
                self.ui.warn("invalid format — skipping"); fail_count += 1; continue

            end = self.ui.ask(f"end time for clip {i} (HH:MM:SS or MM:SS)")
            if end.lower() == 'q':
                break
            if not self._validate_time(end):
                self.ui.warn("invalid format — skipping"); fail_count += 1; continue

            result = self.downloader.download_youtube(
                yt_url, download_type=dt, start_time=start, end_time=end
            )

            if result and result.get("status") == "success":
                self.ui.success(f"clip {i} forged → {result['filename']}",
                                detail=f"{start}  →  {end}")
                ok_count += 1
                self.files_downloaded += 1
                self.downloader.run_clipforge_process(result['filename'], yt_url)
            else:
                err = result.get('error', 'unknown') if result else 'unknown'
                self.ui.error(f"clip {i} failed", hints=[err])
                fail_count += 1

        self.ui.panel(
            f"[{T.SUCCESS}]{I.SUCCESS}  successful  {ok_count}[/]\n"
            f"[{T.ERROR}]{I.ERROR}  failed      {fail_count}[/]\n"
            f"[{T.DIM}]{I.INFO}  total       {ok_count + fail_count}[/]",
            title=f"[{T.MAGENTA}] clipforge session [/]",
            border=T.BORDER_FORGE,
        )

    def handle_thumbnail(self):
        url = self.ui.ask("youtube video url")
        if url.lower() == 'q' or not url.strip():
            return
        with self.ui.status("fetching thumbnail …", "earth"):
            result = self.downloader.download_youtube_thumbnail(url)
        self._show_result(result)

    def _exit_screen(self):
        elapsed = datetime.now() - self.session_start
        mins    = int(elapsed.total_seconds() // 60)
        secs    = int(elapsed.total_seconds() % 60)
        self.ui.blank()
        self.ui.panel(
            f"[{T.ACCENT}]{I.STAR}  session complete[/]\n\n"
            f"  [{T.DIM}]downloaded   [{T.SUCCESS}]{self.files_downloaded} file(s)[/][/]\n"
            f"  [{T.DIM}]duration     [{T.WHITE}]{mins}m {secs}s[/][/]\n\n"
            f"[{T.DIM}]goodbye — by Abubaker Khalid[/]",
            title=f"[{T.ACCENT}] mediadhob [/]",
            border=T.BORDER_MAIN,
        )
        time.sleep(0.8)

    def run(self):
        self.console.clear()
        render_banner(self.ui)
        render_statusbar(self.ui, self.downloader.save_dir, self.files_downloaded)

        HANDLERS = {
            "1": self.handle_instagram,
            "2": self.handle_youtube,
            "3": self.handle_youtube_segment,
            "4": self.handle_batch,
            "5": self.handle_cookies_refresh,
            "6": self.handle_change_dir,
            "7": self.handle_clipforge,
            "8": self.handle_thumbnail,
        }

        while True:
            render_menu(self.ui)
            choice = self.ui.ask_choice(
                "select command",
                ["1", "2", "3", "4", "5", "6", "7", "8", "q"],
                default="2",
            )

            if choice == "q":
                self._exit_screen()
                break

            handler = HANDLERS.get(choice)
            if handler:
                self.ui.blank()
                try:
                    handler()
                except KeyboardInterrupt:
                    self.ui.warn("operation cancelled")

            # مسح كامل مثل cls — شاشة نظيفة تماماً
            self.console.clear()
            render_statusbar(self.ui, self.downloader.save_dir, self.files_downloaded)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    parser = argparse.ArgumentParser(description="MEDIADHOB — Advanced Media Downloader")
    parser.add_argument("--save-dir", help="directory to save downloaded media", default=None)
    args = parser.parse_args(argv)
    configure_runtime()

    try:
        app = AppUI(save_dir=args.save_dir)
        app.run()
    except KeyboardInterrupt:
        Console().print(f"\n[{T.DIM}]interrupted — goodbye[/]")
    except Exception as e:
        Console().print(f"\n[{T.ERROR}]{I.ERROR}  unexpected error: {e}[/]")
        logging.error(f"fatal error: {e}")

if __name__ == "__main__":
    main()