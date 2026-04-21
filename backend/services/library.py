import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from mutagen import File as MutagenFile
from backend.models import LibraryEntry

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

@dataclass
class LibraryIndex:
    entries: list[LibraryEntry] = field(default_factory=list)

def _parse_filename(path: Path) -> tuple[str, str]:
    stem = path.stem
    if " - " in stem:
        parts = stem.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return "", stem.strip()

def _read_tags(path: Path) -> dict:
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            return {}
        tags = {}
        if "title" in audio:
            tags["title"] = str(audio["title"][0])
        if "artist" in audio:
            tags["artist"] = str(audio["artist"][0])
        if "isrc" in audio:
            tags["isrc"] = str(audio["isrc"][0])
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            tags["duration_s"] = float(audio.info.length)
        return tags
    except Exception:
        return {}

def scan_library(library_dir: Path) -> LibraryIndex:
    entries = []
    for path in library_dir.iterdir():
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        tags = _read_tags(path)
        title = tags.get("title", "")
        artist = tags.get("artist", "")
        duration_s = tags.get("duration_s", 0.0)
        isrc = tags.get("isrc")
        if not title or not artist:
            fn_artist, fn_title = _parse_filename(path)
            if not title:
                title = fn_title
            if not artist:
                artist = fn_artist
        if not title:
            title = path.stem
        entries.append(LibraryEntry(
            title=title, artist=artist, audio_path=str(path),
            duration_s=duration_s, isrc=isrc,
        ))
    return LibraryIndex(entries=entries)

def _similarity(a: str, b: str) -> float:
    words_a = set(normalize_text(a).split())
    words_b = set(normalize_text(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)

def match_track(meta, index: LibraryIndex):
    if meta.isrc:
        for entry in index.entries:
            if entry.isrc and entry.isrc.upper() == meta.isrc.upper():
                return entry
    best_match = None
    best_score = 0.0
    for entry in index.entries:
        title_sim = _similarity(meta.title, entry.title)
        artist_sim = _similarity(" ".join(meta.artists), entry.artist)
        combined = title_sim * 0.6 + artist_sim * 0.4
        if combined > best_score:
            best_score = combined
            best_match = entry
    if best_score >= 0.7:
        return best_match
    norm_title = normalize_text(meta.title)
    norm_artist = normalize_text(meta.artists[0]) if meta.artists else ""
    for entry in index.entries:
        norm_path = normalize_text(Path(entry.audio_path).stem)
        if norm_title in norm_path and (not norm_artist or norm_artist in norm_path):
            return entry
    return None

def save_index(index: LibraryIndex, library_dir: Path):
    data = [e.model_dump() for e in index.entries]
    index_path = library_dir / ".index.json"
    index_path.write_text(json.dumps(data, indent=2))

def load_cached_index(library_dir: Path) -> LibraryIndex | None:
    index_path = library_dir / ".index.json"
    if not index_path.exists():
        return None
    try:
        data = json.loads(index_path.read_text())
        entries = [LibraryEntry(**e) for e in data]
        return LibraryIndex(entries=entries)
    except Exception:
        return None
