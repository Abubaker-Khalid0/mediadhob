"""
tui.py — Professional Textual TUI for MEDIADHOB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Inspired by torlink's dark-panel aesthetic: sidebar navigation,
URL input bar, downloads table, and a keybinding footer.
"""

import os
import json
import argparse
from datetime import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.screen import ModalScreen
from textual.widgets import (
    Static, Input, DataTable, Footer,
    RichLog, Button,
)
from rich.text import Text
from mediadhob.config import configure_runtime


VERSION = "0.2.0"


# ══════════════════════════════════════════════════════════════════════════════
#  GRADIENT TEXT HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def gradient_text(text: str, stops=None, bold: bool = False) -> Text:
    """Apply a smooth horizontal multi-stop gradient across a single line."""
    stops = stops or ["#7dcfff", "#7aa2f7", "#bb9af7", "#f7768e"]
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


# ══════════════════════════════════════════════════════════════════════════════
#  BANNER
# ══════════════════════════════════════════════════════════════════════════════

BANNER_LINES = [
    r" ███╗   ███╗███████╗██████╗ ██╗ █████╗ ██████╗ ██╗  ██╗ ██████╗ ██████╗ ",
    r" ████╗ ████║██╔════╝██╔══██╗██║██╔══██╗██╔══██╗██║  ██║██╔═══██╗██╔══██╗",
    r" ██╔████╔██║█████╗  ██║  ██║██║███████║██║  ██║███████║██║   ██║██████╔╝",
    r" ██║╚██╔╝██║██╔══╝  ██║  ██║██║██╔══██║██║  ██║██╔══██║██║   ██║██╔══██╗",
    r" ██║ ╚═╝ ██║███████╗██████╔╝██║██║  ██║██████╔╝██║  ██║╚██████╔╝██████╔╝",
    r" ╚═╝     ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═════╝",
]


# ══════════════════════════════════════════════════════════════════════════════
#  FORMAT SELECTION MODAL
# ══════════════════════════════════════════════════════════════════════════════

class FormatModal(ModalScreen[str]):
    """Modal dialog for selecting download format."""

    DEFAULT_CSS = """
    FormatModal {
        align: center middle;
    }
    #format-dialog {
        width: 55;
        height: auto;
        background: #1f2335;
        border: solid #5d7bf0;
        padding: 1 2;
    }
    #format-title {
        text-align: center;
        text-style: bold;
        color: #bb9af7;
        padding-bottom: 1;
    }
    .fmt-btn {
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="format-dialog"):
            yield Static("✧ Output Format", id="format-title")
            yield Button("⤓  Video + Audio  (best mp4)", id="btn-va", variant="primary", classes="fmt-btn")
            yield Button("►  Video Only     (no audio)", id="btn-vo", classes="fmt-btn")
            yield Button("♪  Audio Only     (m4a)", id="btn-ao", classes="fmt-btn")
            yield Button("⏻  Cancel", id="btn-cancel", variant="error", classes="fmt-btn")

    @on(Button.Pressed, "#btn-va")
    def select_va(self) -> None:
        self.dismiss("video+audio")

    @on(Button.Pressed, "#btn-vo")
    def select_vo(self) -> None:
        self.dismiss("video_only")

    @on(Button.Pressed, "#btn-ao")
    def select_ao(self) -> None:
        self.dismiss("audio_only")

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")


# ══════════════════════════════════════════════════════════════════════════════
#  COOKIE REFRESH MODAL
# ══════════════════════════════════════════════════════════════════════════════

class CookieModal(ModalScreen[str]):
    """Modal for Instagram cookie refresh options."""

    DEFAULT_CSS = """
    CookieModal {
        align: center middle;
    }
    #cookie-dialog {
        width: 55;
        height: auto;
        background: #1f2335;
        border: solid #5d7bf0;
        padding: 1 2;
    }
    #cookie-title {
        text-align: center;
        text-style: bold;
        color: #bb9af7;
        padding-bottom: 1;
    }
    .cookie-btn {
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="cookie-dialog"):
            yield Static("⚙ Instagram Cookie Refresh", id="cookie-title")
            yield Button("⟳  Auto Login (Private API)", id="btn-auto", variant="primary", classes="cookie-btn")
            yield Button("⛓  Paste sessionid manually", id="btn-manual", classes="cookie-btn")
            yield Button("⏻  Cancel", id="btn-cancel", variant="error", classes="cookie-btn")

    @on(Button.Pressed, "#btn-auto")
    def auto_login(self) -> None:
        self.dismiss("auto")

    @on(Button.Pressed, "#btn-manual")
    def manual(self) -> None:
        self.dismiss("manual")

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")


# ══════════════════════════════════════════════════════════════════════════════
#  SESSIONID INPUT MODAL
# ══════════════════════════════════════════════════════════════════════════════

class SessionIdModal(ModalScreen[str]):
    """Modal for pasting sessionid manually."""

    DEFAULT_CSS = """
    SessionIdModal {
        align: center middle;
    }
    #sid-dialog {
        width: 65;
        height: auto;
        background: #1f2335;
        border: solid #5d7bf0;
        padding: 1 2;
    }
    #sid-title {
        text-align: center;
        text-style: bold;
        color: #bb9af7;
        padding-bottom: 1;
    }
    #sid-help {
        color: #565f89;
        padding-bottom: 1;
    }
    #sid-input {
        margin-bottom: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="sid-dialog"):
            yield Static("⛓ Paste sessionid", id="sid-title")
            yield Static(
                "Open instagram.com → F12 → Application → Cookies → sessionid",
                id="sid-help"
            )
            yield Input(placeholder="paste sessionid value here...", id="sid-input", password=True)
            yield Button("✔  Save", id="btn-save", variant="success")
            yield Button("⏻  Cancel", id="btn-cancel", variant="error")

    @on(Input.Submitted, "#sid-input")
    def submit_input(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    @on(Button.Pressed, "#btn-save")
    def save(self) -> None:
        val = self.query_one("#sid-input", Input).value.strip()
        self.dismiss(val)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss("")

    def action_cancel(self) -> None:
        self.dismiss("")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════

class MediadhobApp(App):
    """MEDIADHOB — Professional Media Toolkit TUI."""

    CSS_PATH = "tui.tcss"
    TITLE = "mediadhob"

    BINDINGS = [
        Binding("slash", "focus_search", "/ Search", show=True),
        Binding("d", "download", "d Download", show=True),
        Binding("r", "refresh_cookies", "r Refresh", show=True),
        Binding("s", "settings_action", "s Settings", show=True),
        Binding("tab", "switch_panel", "tab Switch", show=True),
        Binding("question_mark", "show_help", "? Keys", show=True),
        Binding("q", "quit_app", "q Quit", show=True),
    ]

    def __init__(self, save_dir: str = None):
        super().__init__()
        self.save_dir = save_dir or os.environ.get('SAVE_PATH', 'downloaded_media')
        self.username = os.environ.get('INSTA_USER')
        self.password = os.environ.get('INSTA_PASS')
        self.downloads_count = 0
        self.current_filter = "all"
        self._downloader = None
        self._metadata = []
        self._load_metadata()

    def _load_metadata(self):
        """Load download history from metadata.json."""
        meta_file = os.path.join(self.save_dir, 'metadata.json')
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._metadata = data
                        self.downloads_count = len(data)
            except (json.JSONDecodeError, IOError):
                self._metadata = []

    def _get_downloader(self):
        """Lazy-init the MediaDownloader."""
        if self._downloader is None:
            from mediadhob.main import MediaDownloader, UIHelper
            from rich.console import Console
            console = Console(quiet=True)
            ui = UIHelper(console)
            self._downloader = MediaDownloader(
                console, ui,
                username=self.username,
                password=self.password,
                save_dir=self.save_dir,
            )
        return self._downloader

    def compose(self) -> ComposeResult:
        with Horizontal(id="app-layout"):
            # ── Sidebar ──
            with Vertical(id="sidebar"):
                yield Static(id="sidebar-brand")
                yield Button("▪ All", id="nav-all", classes="nav-item -active")
                yield Button("◆ Instagram", id="nav-instagram", classes="nav-item")
                yield Button("► YouTube", id="nav-youtube", classes="nav-item")
                yield Button("✦ ClipForge", id="nav-clips", classes="nav-item")
                yield Button("▣ Thumbnails", id="nav-thumbs", classes="nav-item")
                yield Static("", classes="nav-spacer")
                yield Button("⌂ Downloads", id="nav-downloads", classes="nav-item")
                yield Button("⚙ Settings", id="nav-settings", classes="nav-item")

            # ── Main content ──
            with Vertical(id="main-content"):
                # Banner
                yield Static(id="banner")

                # URL input (like torlink's search box)
                with Vertical(id="url-box"):
                    yield Static(id="url-label")
                    yield Input(
                        placeholder="Search or paste a URL...",
                        id="url-input",
                    )

                # Downloads table (like torlink's latest panel)
                with Vertical(id="table-box"):
                    yield Static(id="table-title")
                    yield Static(id="table-subtitle")
                    yield DataTable(id="downloads-table")

                # Log panel
                yield RichLog(id="log-panel", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize widgets after mount."""
        # Banner with gradient
        banner_widget = self.query_one("#banner", Static)
        banner_parts = []
        for line in BANNER_LINES:
            banner_parts.append(gradient_text(line, bold=True))
        combined = Text()
        for part in banner_parts:
            combined.append_text(part)
            combined.append("\n")
        banner_widget.update(combined)

        # Sidebar brand
        brand = self.query_one("#sidebar-brand", Static)
        brand_text = Text()
        brand_text.append(" ⚡", style="bold #73daca")
        brand_text.append(" MEDIADHOB", style="bold #bb9af7")
        brand.update(brand_text)

        # URL label
        url_label = self.query_one("#url-label", Static)
        url_label.update(Text("❯ Search", style="bold #7aa2f7"))

        # Table title
        self._update_table_title()

        # Table subtitle
        sub = self.query_one("#table-subtitle", Static)
        sub.update(Text("  newest across all sources", style="#565f89"))

        # Setup table
        table = self.query_one("#downloads-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("#", "Name", "Size", "Platform", "Type", "Date")
        self._populate_table()

        # Welcome log
        log = self.query_one("#log-panel", RichLog)
        log.write(Text("✧ MEDIADHOB v0.2.0 ready", style="bold #bb9af7"))
        log.write(Text(f"  ⌂ {self.save_dir}", style="#565f89"))
        if self.username:
            log.write(Text(f"  ◆ instagram: {self.username}", style="#73daca"))
        else:
            log.write(Text("  ▲ INSTA_USER not set — use [r] to refresh cookies", style="#e0af68"))
        log.write(Text("  ℹ / = search  d = download  r = refresh  ? = help", style="#7dcfff"))

    def _update_table_title(self):
        title = self.query_one("#table-title", Static)
        title.update(Text(f"── Latest ({self.downloads_count}) ──", style="bold #7aa2f7"))

    def _populate_table(self, filter_platform: str = "all"):
        """Fill the downloads table from metadata."""
        table = self.query_one("#downloads-table", DataTable)
        table.clear()

        entries = list(reversed(self._metadata))  # newest first

        if filter_platform not in ("all", "downloads", "settings"):
            platform_map = {
                "instagram": ["instagram"],
                "youtube": ["youtube"],
                "clips": ["youtube"],
                "thumbs": ["youtube_thumbnail"],
            }
            allowed = platform_map.get(filter_platform, [])
            entries = [e for e in entries if e.get("platform") in allowed]
            if filter_platform == "clips":
                entries = [e for e in entries if e.get("start_time")]

        for i, entry in enumerate(entries[:25], 1):  # show last 25
            name = entry.get("title") or os.path.basename(entry.get("filename", "?"))
            if len(name) > 30:
                name = name[:27] + "…"

            platform = entry.get("platform", "?")
            dl_type = entry.get("download_type", "?")
            ts = entry.get("timestamp", "")
            date_str = ts[:10] if ts else "—"

            # File size
            fpath = entry.get("filename", "")
            if os.path.exists(fpath):
                size_bytes = os.path.getsize(fpath)
                if size_bytes > 1_073_741_824:
                    size = f"{size_bytes / 1_073_741_824:.2f} GB"
                elif size_bytes > 1_048_576:
                    size = f"{size_bytes / 1_048_576:.1f} MB"
                else:
                    size = f"{size_bytes / 1024:.0f} KB"
            else:
                size = "—"

            # Color-coded platform
            pf_upper = platform.upper()
            if "INSTAGRAM" in pf_upper:
                pf_text = Text(pf_upper, style="bold #f7768e")
            elif "THUMBNAIL" in pf_upper:
                pf_text = Text("THUMB", style="bold #e0af68")
            else:
                pf_text = Text(pf_upper, style="bold #73daca")

            table.add_row(
                str(i),
                name,
                size,
                pf_text,
                dl_type,
                date_str,
            )

        self._update_table_title()

    # ══════════════════════════════════════════════════════════════════════════
    #  ACTIONS (keybindings)
    # ══════════════════════════════════════════════════════════════════════════

    def action_focus_search(self) -> None:
        self.query_one("#url-input", Input).focus()

    def action_download(self) -> None:
        url_input = self.query_one("#url-input", Input)
        url = url_input.value.strip()
        if not url:
            self._log("▲ enter a URL first (press / to focus)", "#e0af68")
            url_input.focus()
            return
        self._start_download(url)

    def action_settings_action(self) -> None:
        self._log(f"⚙ save dir: {self.save_dir}", "#bb9af7")
        self._log("  edit .env SAVE_PATH or use --save-dir flag", "#565f89")

    def action_refresh_cookies(self) -> None:
        self.push_screen(CookieModal(), self._handle_cookie_result)

    def action_switch_panel(self) -> None:
        url_input = self.query_one("#url-input", Input)
        table = self.query_one("#downloads-table", DataTable)
        if url_input.has_focus:
            table.focus()
        else:
            url_input.focus()

    def action_quit_app(self) -> None:
        self.exit()

    def action_show_help(self) -> None:
        log = self.query_one("#log-panel", RichLog)
        log.write(Text(""))
        log.write(Text("── Keybindings ──", style="bold #7aa2f7"))
        log.write(Text("  /       focus URL input", style="#a9b1d6"))
        log.write(Text("  d       download current URL", style="#a9b1d6"))
        log.write(Text("  r       refresh IG cookies", style="#a9b1d6"))
        log.write(Text("  s       settings info", style="#a9b1d6"))
        log.write(Text("  tab     switch focus", style="#a9b1d6"))
        log.write(Text("  enter   submit URL", style="#a9b1d6"))
        log.write(Text("  q       quit", style="#a9b1d6"))
        log.write(Text("─────────────────", style="#3b4261"))

    # ══════════════════════════════════════════════════════════════════════════
    #  EVENTS
    # ══════════════════════════════════════════════════════════════════════════

    @on(Input.Submitted, "#url-input")
    def on_url_submitted(self, event: Input.Submitted) -> None:
        url = event.value.strip()
        if url:
            self._start_download(url)

    @on(Button.Pressed, ".nav-item")
    def on_nav_pressed(self, event: Button.Pressed) -> None:
        """Handle sidebar navigation."""
        item_id = event.button.id.replace("nav-", "") if event.button.id else ""

        # Update active state
        for btn in self.query(".nav-item"):
            btn.remove_class("-active")
        event.button.add_class("-active")

        if item_id == "settings":
            self.action_settings_action()
            return

        self.current_filter = item_id
        self._populate_table(item_id)

    # ══════════════════════════════════════════════════════════════════════════
    #  DOWNLOAD LOGIC
    # ══════════════════════════════════════════════════════════════════════════

    def _start_download(self, url: str) -> None:
        """Detect platform and prompt for format."""
        if "instagram.com" in url or "instagr.am" in url:
            self._pending_url = url
            self._pending_platform = "instagram"
            self.push_screen(FormatModal(), self._handle_format_result)
        elif "youtube.com" in url or "youtu.be" in url:
            self._pending_url = url
            self._pending_platform = "youtube"
            self.push_screen(FormatModal(), self._handle_format_result)
        else:
            self._log("✘ unsupported URL — only Instagram & YouTube", "#f7768e")

    def _handle_format_result(self, fmt: str) -> None:
        if not fmt:
            self._log("  cancelled", "#565f89")
            return
        self._do_download(self._pending_url, self._pending_platform, fmt)

    @work(thread=True)
    def _do_download(self, url: str, platform: str, fmt: str) -> None:
        """Run download in worker thread."""
        self.call_from_thread(
            self._log, f"⤓ downloading [{platform}] ({fmt})…", "#7dcfff"
        )

        try:
            dl = self._get_downloader()
            if platform == "instagram":
                result = dl.download_instagram(url, download_type=fmt)
            else:
                result = dl.download_youtube(url, download_type=fmt)

            if result and result.get("status") == "success":
                filename = result.get("filename", "")
                title = result.get("metadata", {}).get("title", "")
                display = title or os.path.basename(filename)
                if len(display) > 50:
                    display = display[:47] + "…"
                self.call_from_thread(
                    self._log, f"✔ {display}", "#73daca"
                )
                self.call_from_thread(
                    self._log, f"  → {filename}", "#565f89"
                )
                self.downloads_count += 1
                self._load_metadata()
                self.call_from_thread(self._populate_table, self.current_filter)
                self.call_from_thread(self._clear_input)
            else:
                err = result.get("error", "unknown") if result else "unknown"
                self.call_from_thread(
                    self._log, f"✘ {err}", "#f7768e"
                )
        except Exception as e:
            self.call_from_thread(
                self._log, f"✘ error: {e}", "#f7768e"
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  COOKIE LOGIC
    # ══════════════════════════════════════════════════════════════════════════

    def _handle_cookie_result(self, method: str) -> None:
        if not method:
            return
        if method == "auto":
            self._do_cookie_auto()
        else:
            self.push_screen(SessionIdModal(), self._handle_sessionid)

    def _handle_sessionid(self, sid: str) -> None:
        if not sid:
            return
        self._do_cookie_manual(sid)

    @work(thread=True)
    def _do_cookie_auto(self) -> None:
        self.call_from_thread(self._log, "⟳ refreshing cookies (Private API)…", "#7dcfff")
        try:
            dl = self._get_downloader()
            dl.refresh_instagram_cookies()
            self.call_from_thread(
                self._log, "✔ cookies refreshed successfully", "#73daca"
            )
        except Exception as e:
            self.call_from_thread(
                self._log, f"✘ refresh failed: {e}", "#f7768e"
            )

    @work(thread=True)
    def _do_cookie_manual(self, sid: str) -> None:
        self.call_from_thread(self._log, "⛓ saving sessionid…", "#7dcfff")
        try:
            dl = self._get_downloader()
            dl.refresh_instagram_cookies_manual(sid)
            self.call_from_thread(
                self._log, "✔ sessionid saved", "#73daca"
            )
        except Exception as e:
            self.call_from_thread(
                self._log, f"✘ failed: {e}", "#f7768e"
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, message: str, style: str = "#a9b1d6") -> None:
        log = self.query_one("#log-panel", RichLog)
        log.write(Text(message, style=style))

    def _clear_input(self) -> None:
        self.query_one("#url-input", Input).value = ""


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def run(argv=None):
    """Entry point for the TUI application."""
    parser = argparse.ArgumentParser(description="MEDIADHOB — Advanced Media Downloader TUI")
    parser.add_argument("--save-dir", help="directory to save downloaded media", default=None)
    parser.add_argument("--classic", action="store_true", help="use classic Rich-based UI")
    args = parser.parse_args(argv)
    classic_args = ["--save-dir", args.save_dir] if args.save_dir else []

    if args.classic:
        from mediadhob.main import main
        main(classic_args)
        return

    configure_runtime()

    # Check terminal support
    import sys
    if sys.platform == "win32":
        # Enable VT100 escape sequences on Windows
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(
            kernel32.GetStdHandle(-11), 7  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        )

    try:
        app = MediadhobApp(save_dir=args.save_dir)
        app.run()
    except Exception as e:
        print(f"\n[!] Textual TUI failed: {e}")
        print("[*] Falling back to classic interface...\n")
        from mediadhob.main import main
        main(classic_args)


if __name__ == "__main__":
    run()
