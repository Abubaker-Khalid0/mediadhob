# MEDIADHOB

A terminal media downloader for YouTube and Instagram, with a Textual interface
and a classic Rich interface. Python 3.11 or newer is required.

## Features

- Download YouTube videos, audio, or video without audio.
- Download Instagram videos using your own login session.
- Browse download history in the terminal interface.
- Use the classic interface for batch URLs, timestamp trimming, thumbnails,
  ClipForge, changing the save directory, and subtitles.
- Fetch YouTube subtitles or optionally generate them locally with faster-whisper.
- Burn Arabic or English captions with the included Lateef and Lato fonts.

## Requirements

- Python **3.11+**, with `pip` and `venv`.
- [FFmpeg and ffprobe](https://ffmpeg.org/download.html) on `PATH` for merging,
  trimming, audio conversion, and captions. Subtitle burning needs an FFmpeg
  build with the `subtitles` filter (libass).
- Internet access for downloads and Instagram authentication. The optional
  transcription model is downloaded on first use.

Check your installation with `python --version`, `ffmpeg -version`, and
`ffprobe -version` (`python3` may be the Python command on macOS/Linux).

## Install from this repository

Clone this repository or download and extract its source ZIP, then open a
terminal inside the project directory.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\mediadhob.exe
```

Alternatively, run `.\install.bat`. It creates a local virtual environment
and installs the project there without administrator access.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/mediadhob
```

Alternatively, run `bash Install.sh` (the filename is case-sensitive).
On Linux, install your distribution's Python venv package if `venv` is missing.

Activate the virtual environment to use the short commands below:

```powershell
# Windows PowerShell (direct .venv commands also work without activation)
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

### Optional local transcription

From the project directory, with the virtual environment active:

```bash
python -m pip install ".[captions]"
```

Without this extra, downloading and fetching existing YouTube subtitles still
work. Local transcription can be slow on a CPU and requires model storage.

## Usage

```bash
mediadhob
mediadhob --save-dir "path/to/downloads"
mediadhob --classic
mediadhob-classic --save-dir "path/to/downloads"
python -m mediadhob --help
```

In the Textual interface, paste a URL and press Enter. Use `r` for Instagram
session setup and `?` for keyboard shortcuts. Use `mediadhob-classic` for the
full numbered menu, including batch downloads, ClipForge, and captions.

If a terminal cannot render the Textual interface, use the classic interface.
Windows Terminal is suitable for the Unicode interface.

## Optional configuration

YouTube use does not require Instagram credentials or a `.env` file. To configure
Instagram or a default save path, copy `.env.example` to `.env` in the directory
**from which you launch the application**:

```powershell
# Windows
Copy-Item .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

Fill in only the values you need. Existing environment variables take precedence.

| Setting | Purpose |
| --- | --- |
| `INSTA_USER` | Your Instagram username; optional for manual session setup. |
| `INSTA_PASS` | Your Instagram password; optional for manual session setup. |
| `SAVE_PATH` | Download directory; defaults to `downloaded_media`. |
| `IG_PROXY` | Optional proxy URL for Instagram authentication. |

`--save-dir` overrides `SAVE_PATH`. Relative paths resolve from the launch
folder. The classic interface can persist a new save path in that folder's `.env`.

For manual Instagram setup, press `r` in the TUI or choose option `5` in the
classic interface, then paste your own browser's `sessionid`. This input is
masked. Never share session IDs. If Instagram requests two-factor authentication
or account verification, use the classic interface or manual session setup.
Instagram may reject automated logins; credentials do not guarantee access.

## Local files and privacy

The application creates these files as needed in the launch directory:

- `cookies.txt` and `ig_session.json`: sensitive Instagram session data.
- `media_downloader.log`: diagnostics that can contain URLs and local filenames.
- `downloaded_media/`: default downloads and `metadata.json` history.

These files, local environments, and common downloaded media formats are ignored
by Git. If you choose another save directory, keep its contents out of commits
as well. Session files are plaintext; see [SECURITY.md](SECURITY.md).

The source distribution and wheel contain no bundled credentials, login sessions,
or downloaded media. Use this project only for content you own or are authorized
to download and in accordance with the relevant service's terms.

## Development

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m build
python tests/check_distribution.py dist
```

Tests are offline and use synthetic data. See [CONTRIBUTING.md](CONTRIBUTING.md)
for contribution guidance. Download compatibility also depends on upstream
services; update the installed downloader when needed:

```bash
python -m pip install --upgrade yt-dlp
```

## License

Application code: [MIT](LICENSE), by Abubaker Khalid.
Bundled fonts: SIL Open Font License 1.1; see
[third-party notices](THIRD_PARTY_NOTICES.md).
