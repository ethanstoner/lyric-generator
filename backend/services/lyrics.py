import logging
import re
import time
import requests
from backend.models import TimedLine, TimedWord
from backend.config import settings

logger = logging.getLogger(__name__)

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

def _lrclib_get(url: str, params: dict, retries: int = 2) -> object | None:
    """GET lrclib with a short retry on transient network/5xx failures."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url, params=params,
                headers={"User-Agent": "LyricVideoGenerator/1.0"},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None  # definitive miss — don't retry
            logger.warning("LRCLIB %s returned HTTP %s", url, resp.status_code)
        except requests.RequestException as e:
            logger.warning("LRCLIB request failed (attempt %d): %s", attempt + 1, e)
        if attempt < retries:
            time.sleep(1.0 * (attempt + 1))
    return None

def fetch_lrclib(title: str, artist: str, duration_s: int) -> tuple[str | None, str | None] | None:
    data = _lrclib_get(
        "https://lrclib.net/api/get",
        {"artist_name": artist, "track_name": title, "duration": duration_s},
    )
    if isinstance(data, dict):
        synced, plain = data.get("syncedLyrics"), data.get("plainLyrics")
        if synced or plain:
            return (synced, plain)

    results = _lrclib_get(
        "https://lrclib.net/api/search",
        {"track_name": title, "artist_name": artist},
    )
    if isinstance(results, list) and results:
        best = results[0]
        synced, plain = best.get("syncedLyrics"), best.get("plainLyrics")
        if synced or plain:
            return (synced, plain)
    return None

def _plain_to_lines(plain: str, duration_s: float) -> list[TimedLine]:
    """Distribute plain (un-timed) lyric lines evenly across the song so the
    video still shows lyrics when no synced timing is available."""
    raw = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    if not raw:
        return []
    per = max(duration_s / len(raw), 0.5)
    return [
        TimedLine(text=t, start=i * per, end=(i + 1) * per, words=None)
        for i, t in enumerate(raw)
    ]

def transcribe_with_whisper(audio_path: str) -> list[TimedLine]:
    import whisper
    device = settings.whisper_device or None
    logger.info("Loading Whisper model '%s' (device=%s)", settings.whisper_model, device or "auto")
    model = whisper.load_model(settings.whisper_model, device=device)
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
        lines = transcribe_with_whisper(audio_path)
        if lines:
            return lines
        logger.warning("Whisper returned no segments; falling back to LRCLIB")
    except Exception as e:
        logger.warning("Whisper transcription failed (%s); falling back to LRCLIB", e)

    duration_s = duration_ms // 1000
    result = fetch_lrclib(title, artist, duration_s)
    if result:
        synced, plain = result
        if synced:
            lines = parse_lrc(synced)
            if lines:
                logger.info("Using LRCLIB synced lyrics (%d lines)", len(lines))
                return lines
        if plain:
            lines = _plain_to_lines(plain, duration_s or 1)
            if lines:
                logger.info("Using LRCLIB plain lyrics (%d lines, estimated timing)", len(lines))
                return lines
    logger.error("No lyrics found for '%s' by '%s'", title, artist)
    return []
