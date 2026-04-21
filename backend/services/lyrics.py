import re
import os
import requests
from backend.models import TimedLine, TimedWord
from backend.config import settings


def strip_adlibs(text: str) -> str:
    """Remove parenthesized adlibs like (yeah), (ooh), etc."""
    return re.sub(r'\s*\([^)]*\)\s*', ' ', text).strip()


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


def _plain_to_timed(plain_text: str, duration_s: int) -> list[TimedLine]:
    """Convert plain (unsynced) lyrics to evenly-spaced TimedLines."""
    raw_lines = [l.strip() for l in plain_text.strip().split("\n") if l.strip()]
    if not raw_lines:
        return []
    interval = duration_s / len(raw_lines)
    lines = []
    for i, text in enumerate(raw_lines):
        start = i * interval
        end = (i + 1) * interval
        lines.append(TimedLine(text=text, start=start, end=end, words=None))
    return lines


def _detect_gpu_memory_gb(torch) -> float:
    if settings.whisper_gpu_memory_gb > 0:
        return settings.whisper_gpu_memory_gb
    if not torch.cuda.is_available():
        return 0.0
    try:
        props = torch.cuda.get_device_properties(0)
        return props.total_memory / (1024 ** 3)
    except Exception:
        return 0.0


def _detect_system_memory_gb() -> float:
    try:
        if os.name == "nt":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            memory_status = MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
                return memory_status.ullTotalPhys / (1024 ** 3)
            return 0.0

        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024 ** 3)
    except Exception:
        return 0.0


def _resolve_whisper_model(device: str, gpu_memory_gb: float) -> str:
    if settings.whisper_model != "auto":
        return settings.whisper_model

    system_memory_gb = _detect_system_memory_gb()

    if device == "cuda":
        if gpu_memory_gb and gpu_memory_gb < 4:
            return "tiny"
        if gpu_memory_gb and gpu_memory_gb < 8:
            return "base"
        return "small"

    if system_memory_gb and system_memory_gb < 8:
        return "tiny"
    if system_memory_gb and system_memory_gb < 16:
        return "base"
    return "small"


def _whisperx_available() -> bool:
    try:
        import whisperx  # noqa: F401
        return True
    except Exception:
        return False


def _resolve_whisper_runtime(torch) -> tuple[str, str, float, str]:
    if settings.whisper_device == "auto":
        if torch.cuda.is_available():
            gpu_memory_gb = _detect_gpu_memory_gb(torch)
            device = "cuda" if not gpu_memory_gb or gpu_memory_gb >= 3 else "cpu"
        else:
            device = "cpu"
    else:
        device = settings.whisper_device

    gpu_memory_gb = _detect_gpu_memory_gb(torch)
    model_name = _resolve_whisper_model(device, gpu_memory_gb)

    if settings.whisper_compute_type != "auto":
        compute_type = settings.whisper_compute_type
    elif device == "cuda":
        # Prefer lighter settings on smaller GPUs to reduce OOM risk.
        compute_type = "int8" if gpu_memory_gb and gpu_memory_gb < 6 else "float16"
    else:
        compute_type = "int8"

    return device, compute_type, gpu_memory_gb, model_name


def _should_retry_on_cpu(exc: Exception) -> bool:
    message = str(exc).lower()
    return "out of memory" in message or "cuda" in message


def _load_whisperx_language_align_model(whisperx, device: str):
    return whisperx.load_align_model(language_code="en", device=device)


def align_with_whisperx(audio_path: str, segments: list[dict], device: str = None) -> list[dict]:
    """Use WhisperX forced alignment to get precise word timestamps.

    Takes LRCLIB lyrics (correct text) + their approximate timing,
    and returns phoneme-accurate word-level timestamps.
    """
    import warnings
    warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")
    import torch
    import whisperx

    if device is None:
        device, _, gpu_memory_gb, _ = _resolve_whisper_runtime(torch)
    else:
        gpu_memory_gb = _detect_gpu_memory_gb(torch) if device == "cuda" else 0.0

    if device == "cuda":
        print(f"       WhisperX align: using CUDA ({gpu_memory_gb:.1f} GB detected)")
    else:
        print("       WhisperX align: using CPU")

    audio = whisperx.load_audio(audio_path)
    try:
        model_a, metadata = _load_whisperx_language_align_model(whisperx, device)
        result = whisperx.align(
            segments, model_a, metadata, audio, device,
            return_char_alignments=False,
        )
        return result["segments"]
    except Exception as exc:
        if device == "cuda" and _should_retry_on_cpu(exc):
            print("       WhisperX align: CUDA failed, retrying on CPU")
            model_a, metadata = _load_whisperx_language_align_model(whisperx, "cpu")
            result = whisperx.align(
                segments, model_a, metadata, audio, "cpu",
                return_char_alignments=False,
            )
            return result["segments"]
        raise


def transcribe_with_whisperx(audio_path: str, device: str = None) -> list[dict]:
    """Transcribe audio with WhisperX (used when no lyrics available).

    Returns aligned segments with word-level timestamps.
    """
    import warnings
    warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")
    import torch
    import whisperx

    if device is None:
        device, compute_type, gpu_memory_gb, model_name = _resolve_whisper_runtime(torch)
    else:
        gpu_memory_gb = _detect_gpu_memory_gb(torch) if device == "cuda" else 0.0
        compute_type = "float16" if device == "cuda" else "int8"
        model_name = _resolve_whisper_model(device, gpu_memory_gb)

    if device == "cuda":
        print(
            f"       WhisperX transcribe: using CUDA ({gpu_memory_gb:.1f} GB detected, model={model_name}, compute_type={compute_type})"
        )
    else:
        print(f"       WhisperX transcribe: using CPU (model={model_name}, compute_type={compute_type})")

    audio = whisperx.load_audio(audio_path)

    try:
        model = whisperx.load_model(model_name, device, compute_type=compute_type)
        result = model.transcribe(audio, language="en")
        model_a, metadata = _load_whisperx_language_align_model(whisperx, device)
        result = whisperx.align(
            result["segments"], model_a, metadata, audio, device,
            return_char_alignments=False,
        )
        return result["segments"]
    except Exception as exc:
        if device == "cuda" and _should_retry_on_cpu(exc):
            print("       WhisperX transcribe: CUDA failed, retrying on CPU with int8")
            cpu_model_name = _resolve_whisper_model("cpu", 0.0)
            model = whisperx.load_model(cpu_model_name, "cpu", compute_type="int8")
            result = model.transcribe(audio, language="en")
            model_a, metadata = _load_whisperx_language_align_model(whisperx, "cpu")
            result = whisperx.align(
                result["segments"], model_a, metadata, audio, "cpu",
                return_char_alignments=False,
            )
            return result["segments"]
        raise


def _distribute_words_evenly(text: str, start: float, end: float) -> list[TimedWord]:
    """Distribute words evenly across [start, end] as a fallback when alignment fails."""
    raw_words = text.split()
    if not raw_words:
        return []
    duration = max(end - start, 0.1)
    word_dur = duration / len(raw_words)
    words = []
    for i, w in enumerate(raw_words):
        w_start = start + i * word_dur
        w_end = w_start + word_dur
        words.append(TimedWord(word=w, start=round(w_start, 3), end=round(w_end, 3)))
    return words


def _whisperx_segments_to_lines(segments: list[dict]) -> list[TimedLine]:
    """Convert WhisperX aligned segments to TimedLine objects.

    Every line is guaranteed to have word-level timing. If WhisperX
    failed to align a segment, words are distributed evenly across
    the line duration as a best-effort fallback.
    """
    lines = []
    for seg in segments:
        words = []
        if "words" in seg:
            for w in seg["words"]:
                # WhisperX may omit start/end for unalignable words
                if "start" not in w or "end" not in w:
                    continue
                words.append(TimedWord(
                    word=w["word"],
                    start=round(w["start"], 3),
                    end=round(w["end"], 3),
                ))

        start = seg.get("start", 0.0)
        end = seg.get("end", start + 1.0)

        # If we have words, use their span for accurate line timing
        if words:
            start = words[0].start
            end = words[-1].end
        else:
            # WhisperX failed to align — distribute words evenly
            text = seg.get("text", "")
            words = _distribute_words_evenly(text, start, end)

        lines.append(TimedLine(
            text=seg.get("text", ""),
            start=round(start, 3),
            end=round(end, 3),
            words=words if words else None,
        ))
    return lines


def get_lyrics(title: str, artist: str, duration_ms: int, audio_path: str,
               align: bool = True) -> list[TimedLine]:
    """Get lyrics with accurate word-level timestamps.

    Pipeline:
    1. Fetch real lyrics from LRCLIB (correct words)
    2. Use WhisperX forced alignment for phoneme-accurate word timestamps
    """
    duration_s = duration_ms // 1000
    whisperx_installed = _whisperx_available()

    # 1. Get real lyrics from LRCLIB
    result = fetch_lrclib(title, artist, duration_s)
    lrc_lines = None

    if result:
        synced, plain = result
        if synced:
            lrc_lines = parse_lrc(synced)
            if lrc_lines:
                print("       Lyrics: LRCLIB (synced)")
        if not lrc_lines and plain:
            lrc_lines = _plain_to_timed(plain, duration_s)
            print("       Lyrics: LRCLIB (plain)")

    if not lrc_lines:
        # No lyrics found -- full WhisperX transcription + alignment
        if not whisperx_installed:
            print("       WhisperX unavailable: install it to transcribe songs without LRCLIB lyrics")
            return []
        print("       Lyrics: WhisperX (no lyrics found)")
        try:
            aligned_segments = transcribe_with_whisperx(audio_path)
        except Exception as e:
            print(f"       WhisperX transcription failed: {e}")
            return []
        return _whisperx_segments_to_lines(aligned_segments)

    if not align or not settings.whisper_align or not whisperx_installed:
        if lrc_lines and not whisperx_installed:
            print("       WhisperX unavailable: using LRCLIB line timing")
        return lrc_lines

    # 2. Build segments from LRCLIB lines for WhisperX forced alignment
    segments = []
    for line in lrc_lines:
        text = strip_adlibs(line.text).strip()
        if not text:
            continue
        segments.append({
            "text": text,
            "start": line.start,
            "end": line.end,
        })

    if not segments:
        return lrc_lines

    print(f"       WhisperX: aligning {len(segments)} segments...")
    try:
        aligned_segments = align_with_whisperx(audio_path, segments)
    except Exception as e:
        print(f"       WhisperX alignment failed: {e}")
        print("       Falling back to LRCLIB line timing")
        return lrc_lines

    lines = _whisperx_segments_to_lines(aligned_segments)
    lines_with_words = sum(1 for l in lines if l.words)
    print(f"       Aligned: {lines_with_words}/{len(lines)} lines with word-level timing")

    return lines
