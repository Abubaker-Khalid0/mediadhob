"""
captions.py — Caption / Subtitle Engine for MEDIADHOB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Strategy:
    1. Try downloading YouTube's built-in subtitles via yt-dlp
    2. If unavailable, fall back to local Whisper transcription (faster-whisper)
    3. Burn subtitles into video using ffmpeg

Supports: Arabic (ar), English (en), or auto-detect.
"""

import os
import re
import glob
import subprocess
import logging
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

# Check if faster-whisper is available
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


class CaptionEngine:
    """
    Handles subtitle download, generation, and embedding.

    Usage:
        engine = CaptionEngine(ui=ui_helper)
        result_path = engine.add_captions(
            video_path="path/to/video.mp4",
            video_url="https://youtube.com/watch?v=...",
            language="ar",
        )
    """

    # Whisper model size — "base" is a good balance of speed/quality
    WHISPER_MODEL = "base"

    def __init__(self, ui=None):
        self.ui = ui
        self._whisper_model = None

    def _log(self, level: str, msg: str):
        getattr(logger, level, logger.info)(msg)
        if self.ui:
            method = getattr(self.ui, level, self.ui.info)
            method(msg)

    # ══════════════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ══════════════════════════════════════════════════════════════════════════

    def add_captions(
        self,
        video_path: str,
        video_url: str = None,
        language: str = "auto",
        burn: bool = True,
    ) -> str | None:
        """
        Add captions to a video file.

        Args:
            video_path: Path to the downloaded video file
            video_url: Original URL (needed for YouTube subtitle fetch)
            language: "ar", "en", or "auto"
            burn: If True, hardcode subs into video; if False, keep .srt alongside

        Returns:
            Path to the captioned video (or .srt file if burn=False), or None on failure.
        """
        if not os.path.exists(video_path):
            self._log("error", f"video not found: {video_path}")
            return None

        srt_path = None

        # ── Strategy 1: YouTube built-in subtitles ──
        if video_url and ("youtube.com" in video_url or "youtu.be" in video_url):
            self._log("info", "trying youtube built-in subtitles …")
            srt_path = self._fetch_youtube_subs(video_url, video_path, language)

        # ── Strategy 2: Whisper local transcription ──
        if not srt_path:
            if not HAS_WHISPER:
                self._log("warn",
                    "no youtube subtitles found & faster-whisper not installed\n"
                    "  install with: pip install faster-whisper"
                )
                return None
            self._log("info", "no built-in subs — generating with whisper …")
            srt_path = self._generate_whisper_subs(video_path, language)

        if not srt_path:
            self._log("error", "could not obtain subtitles from any source")
            return None

        # ── Burn or keep alongside ──
        if burn:
            return self._burn_subtitles(video_path, srt_path, language)
        else:
            self._log("info", f"subtitles saved → {srt_path}")
            return srt_path

    # ══════════════════════════════════════════════════════════════════════════
    #  STRATEGY 1: YouTube built-in subtitles
    # ══════════════════════════════════════════════════════════════════════════

    def _fetch_youtube_subs(self, url: str, video_path: str, language: str) -> str | None:
        """Download YouTube subtitles (manual first, then auto-generated) using yt-dlp Python API."""
        import yt_dlp

        base = os.path.splitext(video_path)[0]
        lang_code = self._resolve_lang(language)

        # Try manual subs first, then auto-generated
        for use_auto in (False, True):
            outtmpl = base + "_subtmp.%(ext)s"
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": not use_auto,
                "writeautomaticsub": use_auto,
                "subtitleslangs": [lang_code],
                "subtitlesformat": "srt/vtt/best",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegSubtitlesConvertor",
                    "format": "srt",
                }],
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Search for generated .srt file
                patterns = [
                    f"{base}_subtmp.{lang_code}.srt",
                    f"{base}_subtmp.{lang_code}*.srt",
                ]
                found = []
                for pat in patterns:
                    found.extend(glob.glob(pat))
                if not found:
                    # Broader search
                    found = glob.glob(f"{base}_subtmp*.srt")

                if found:
                    srt_file = found[0]
                    final_srt = base + ".srt"
                    if os.path.exists(final_srt):
                        os.remove(final_srt)
                    os.rename(srt_file, final_srt)
                    # Cleanup other temp files
                    for f in glob.glob(f"{base}_subtmp*"):
                        try:
                            os.remove(f)
                        except Exception:
                            pass
                    sub_type = "auto-generated" if use_auto else "manual"
                    self._log("info", f"youtube subtitles downloaded ({sub_type}, {lang_code})")
                    return final_srt

            except Exception as e:
                self._log("warn", f"subtitle fetch attempt failed: {e}")

        # Cleanup any leftover temp files
        for f in glob.glob(f"{base}_subtmp*"):
            try:
                os.remove(f)
            except Exception:
                pass

        self._log("info", "no youtube subtitles available for this video")
        return None

    # ══════════════════════════════════════════════════════════════════════════
    #  STRATEGY 2: Whisper local transcription
    # ══════════════════════════════════════════════════════════════════════════

    def _generate_whisper_subs(self, video_path: str, language: str) -> str | None:
        """Transcribe audio using faster-whisper and produce .srt file."""
        if not HAS_WHISPER:
            return None

        try:
            # Load model (cached after first call)
            if self._whisper_model is None:
                self._log("info", f"loading whisper model ({self.WHISPER_MODEL}) — first time may download …")
                self._whisper_model = WhisperModel(
                    self.WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",
                )

            # Determine language
            lang = None if language == "auto" else self._resolve_lang(language)

            self._log("info", "transcribing audio — this may take a moment …")

            segments, info = self._whisper_model.transcribe(
                video_path,
                language=lang,
                beam_size=5,
                vad_filter=True,
            )

            detected_lang = info.language
            self._log("info", f"detected language: {detected_lang} (probability: {info.language_probability:.0%})")

            # Build SRT content
            srt_lines = []
            for i, seg in enumerate(segments, 1):
                start_ts = self._seconds_to_srt_time(seg.start)
                end_ts = self._seconds_to_srt_time(seg.end)
                text = seg.text.strip()
                if text:
                    srt_lines.append(f"{i}")
                    srt_lines.append(f"{start_ts} --> {end_ts}")
                    srt_lines.append(text)
                    srt_lines.append("")

            if not srt_lines:
                self._log("warn", "whisper produced no text — video may have no speech")
                return None

            # Write .srt
            srt_path = os.path.splitext(video_path)[0] + ".srt"
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(srt_lines))

            self._log("info", f"whisper transcription complete → {srt_path}")
            return srt_path

        except Exception as e:
            self._log("error", f"whisper transcription failed: {e}")
            logger.exception("whisper error traceback:")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    #  BURN SUBTITLES INTO VIDEO (ffmpeg)
    # ══════════════════════════════════════════════════════════════════════════

    def _burn_subtitles(self, video_path: str, srt_path: str, language: str = "auto") -> str | None:
        """Hardcode .srt subtitles into video using ffmpeg with custom fonts."""
        base, ext = os.path.splitext(video_path)
        output_path = base + "_captioned" + ext

        # ── Resolve font path based on language ──
        fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
        lang_code = self._resolve_lang(language)

        if lang_code == "ar":
            font_file = os.path.join(fonts_dir, "Lateef-SemiBold.ttf")
            font_name = "Lateef"
            font_size = 28  # Arabic needs slightly larger
        else:
            font_file = os.path.join(fonts_dir, "Lato-Regular.ttf")
            font_name = "Lato"
            font_size = 24

        # Escape paths for ffmpeg subtitles filter (Windows forward-slash + colon escape)
        srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')
        font_escaped = font_file.replace('\\', '/').replace(':', '\\:')

        # Build force_style with custom font
        if os.path.exists(font_file):
            force_style = (
                f"FontName={font_name},"
                f"FontSize={font_size},"
                f"PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,"
                f"Outline=2,Shadow=1,MarginV=30"
            )
            vf_filter = f"subtitles='{srt_escaped}':fontsdir='{os.path.dirname(font_escaped).replace(chr(92), '/')}':force_style='{force_style}'"
        else:
            # Fallback to system font if custom font not found
            self._log("warn", f"custom font not found: {font_file} — using default")
            force_style = "FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=30"
            vf_filter = f"subtitles='{srt_escaped}':force_style='{force_style}'"

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_filter,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            output_path,
        ]

        self._log("info", f"burning subtitles ({font_name}, size {font_size}) …")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                # Fallback: simpler filter without custom font
                self._log("warn", "retrying with simpler subtitle filter …")
                cmd_simple = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vf", f"subtitles='{srt_escaped}'",
                    "-c:a", "copy",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "20",
                    output_path,
                ]
                result = subprocess.run(
                    cmd_simple, capture_output=True, text=True, timeout=600
                )
                if result.returncode != 0:
                    self._log("error", f"ffmpeg subtitle burn failed: {result.stderr[:300]}")
                    return None

            # Replace original with captioned version
            try:
                os.remove(video_path)
                os.rename(output_path, video_path)
                output_path = video_path
            except Exception:
                pass  # Keep _captioned version if rename fails

            # Cleanup .srt
            try:
                os.remove(srt_path)
            except Exception:
                pass

            self._log("info", f"captioned video ready → {output_path}")
            return output_path

        except subprocess.TimeoutExpired:
            self._log("error", "ffmpeg subtitle burn timed out (>10min)")
            return None
        except Exception as e:
            self._log("error", f"subtitle burn error: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _resolve_lang(language: str) -> str:
        """Normalize language input to ISO code."""
        lang_map = {
            "ar": "ar", "arabic": "ar", "عربي": "ar",
            "en": "en", "english": "en",
            "auto": "ar",  # default preference
        }
        return lang_map.get(language.lower().strip(), language.lower().strip())

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def is_whisper_available() -> bool:
        """Check if faster-whisper is installed."""
        return HAS_WHISPER
