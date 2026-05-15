import re
import requests
from backend.models import TimedLine, TimedWord
from backend.config import settings

def parse_lrc(lrc_text: str) -> list[TimedLine]:
    if not lrc_text or not lrc_text.strip():
        return []
    pattern = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)")
    raw_lines = []
    for line in lrc_text.strip().split("\n"):
        match = pattern.match(line.strip())
        if not match:
            continue
        minutes, seconds, centis, text = match.groups()
        if len(centis) == 2:
            frac = int(centis) / 100.0
        else:
            frac = int(centis) / 1000.0
        start = int(minutes) * 60 + int(seconds) + frac
        text = text.strip()
        if not text:
            continue
        raw_lines.append((start, text))
    lines = []
    for i, (start, text) in enumerate(raw_lines):
        if i + 1 < len(raw_lines):
            end = raw_lines[i + 1][0]
        else:
            end = start + 3.0
        lines.append(TimedLine(text=text, start=start, end=end, words=None))
    return lines

def fetch_lrclib(title: str, artist: str, duration_s: int) -> tuple[str | None, str | None] | None:
    try:
        resp = requests.get(
            "https://lrclib.net/api/get",
            params={"artist_name": artist, "track_name": title, "duration": duration_s},
            headers={"User-Agent": "LyricVideoGenerator/1.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            synced = data.get("syncedLyrics")
            plain = data.get("plainLyrics")
            if synced or plain:
                return (synced, plain)
        resp = requests.get(
            "https://lrclib.net/api/search",
            params={"track_name": title, "artist_name": artist},
            headers={"User-Agent": "LyricVideoGenerator/1.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results and len(results) > 0:
                best = results[0]
                synced = best.get("syncedLyrics")
                plain = best.get("plainLyrics")
                if synced or plain:
                    return (synced, plain)
        return None
    except Exception:
        return None

def transcribe_with_whisper(audio_path: str) -> list[TimedLine]:
    import whisper
    model = whisper.load_model(settings.whisper_model)
    result = model.transcribe(audio_path, word_timestamps=True)
    lines = []
    for segment in result.get("segments", []):
        words = []
        if "words" in segment:
            for w in segment["words"]:
                words.append(TimedWord(
                    word=w["word"].strip(), start=w["start"], end=w["end"],
                ))
        lines.append(TimedLine(
            text=segment["text"].strip(), start=segment["start"],
            end=segment["end"], words=words if words else None,
        ))
    return lines

def get_lyrics(title: str, artist: str, duration_ms: int, audio_path: str) -> list[TimedLine]:
    """Always use Whisper for word-level timestamps (typewriter effect).
    LRCLIB is only used as fallback when Whisper fails."""
    try:
        return transcribe_with_whisper(audio_path)
    except Exception:
        # Whisper failed — fall back to LRCLIB line-level
        duration_s = duration_ms // 1000
        result = fetch_lrclib(title, artist, duration_s)
        if result:
            synced, plain = result
            if synced:
                lines = parse_lrc(synced)
                if lines:
                    return lines
        return []
