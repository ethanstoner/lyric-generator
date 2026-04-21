"""
Brat-style Lyric Video Generator
Paste a Spotify link -> types lyrics into bratgenerator.com char by char -> records screen -> outputs MP4.

Usage: python generate_brat.py <spotify_url>
"""
import sys
import os
import re
import io
import time
import subprocess
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
from backend.services.spotify import extract_track_id, fetch_metadata
from backend.services.library import scan_library, match_track, save_index
from backend.services.downloader import download_track
from backend.services.lyrics import get_lyrics, strip_adlibs
from backend.config import LIBRARY_DIR, OUTPUTS_DIR, TEMP_DIR

# Playwright records video at its own pace — there's a delay between when we
# call page.evaluate() and when the DOM change appears in the recorded frame.
# With WhisperX's accurate timestamps, minimal compensation needed.
RENDER_LATENCY = 0


SETUP_JS = """
() => {
    // Switch to white theme
    if (typeof setupTheme === 'function') setupTheme('white');

    // Hide ALL UI except memeContainer
    document.querySelectorAll(
        '.themeSelector, .header, .site-footer, h1, footer, header.header'
    ).forEach(el => el.style.display = 'none');
    document.querySelectorAll('a[href*="howardstirling"]').forEach(el => el.style.display = 'none');
    const footerEl = document.querySelector('footer');
    if (footerEl) footerEl.style.display = 'none';
    const saveMsg = document.getElementById('saveMessage');
    if (saveMsg) saveMsg.style.display = 'none';
    document.querySelectorAll('.node__content > *').forEach(el => {
        if (!el.querySelector('#memeContainer') && el.id !== 'memeContainer') {
            el.style.display = 'none';
        }
    });

    // Hide input visually but keep it focusable for keyboard events
    const input = document.getElementById('textInput');
    input.style.position = 'fixed';
    input.style.top = '-9999px';
    input.style.opacity = '0';

    // Make memeContainer fill viewport
    const mc = document.getElementById('memeContainer');
    mc.style.width = '100vw';
    mc.style.height = '100vh';
    mc.style.position = 'fixed';
    mc.style.top = '0';
    mc.style.left = '0';
    mc.style.zIndex = '99999';
    mc.style.backgroundColor = 'white';
    mc.style.display = 'flex';
    mc.style.alignItems = 'center';
    mc.style.justifyContent = 'center';

    // Center text overlay — must override max-width so textFit uses full container
    const overlay = document.getElementById('textOverlay');
    overlay.style.maxWidth = '80%';
    overlay.style.width = '80%';
    overlay.style.height = '300px';
    overlay.style.position = 'relative';
    overlay.style.top = 'auto';
    overlay.style.left = 'auto';
    overlay.style.transform = 'none';

    document.body.style.overflow = 'hidden';
    document.body.style.backgroundColor = 'white';
    document.body.style.margin = '0';

    // Clear text and focus input
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
}
"""

CLEAR_AND_REFOCUS_JS = """
() => {
    const input = document.getElementById('textInput');
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
}
"""

TYPE_CHAR_JS = """
(char) => {
    const input = document.getElementById('textInput');
    input.value += char;
    input.dispatchEvent(new Event('input', { bubbles: true }));
}
"""

SCHEDULE_TYPING_JS = """
(events) => {
    // events: array of [timeMs, action, char]
    // action: 0 = type char, 1 = clear
    // Schedules ALL typing via setTimeout for frame-accurate timing.
    // Returns immediately — caller sleeps for the duration.
    const input = document.getElementById('textInput');
    const inputEvent = new Event('input', { bubbles: true });

    for (const [timeMs, action, char] of events) {
        setTimeout(() => {
            if (action === 1) {
                input.value = '';
            } else {
                input.value += char;
            }
            input.dispatchEvent(inputEvent);
        }, timeMs);
    }
}
"""


def _estimate_brat_lines(text):
    """Estimate how many visual lines text takes on bratgenerator.com.
    Brat uses ~80% viewport width with textFit. Roughly 18-22 chars per line."""
    words = text.split()
    if not words:
        return 0
    lines = 1
    current_len = 0
    for w in words:
        needed = (1 if current_len > 0 else 0) + len(w)
        if current_len > 0 and current_len + needed > 20:
            lines += 1
            current_len = len(w)
        else:
            current_len += needed
    return lines


def _build_typing_events(lines, total_duration):
    """Build a list of typing events: (time, action, char).

    Always char-by-char — typing speed adapts to match how fast the artist sings.
    Clears on verse/section boundaries (timing gaps between lines).
    Max 4 visual lines on screen before clearing.
    """
    events = []
    MAX_VISUAL_LINES = 4    # max lines on bratgenerator before clearing
    MIN_CHAR_GAP = 0.005    # minimum gap between evaluate() calls
    screen_text = ""         # accumulated text currently on screen
    line_count = 0           # number of lyric lines on screen

    for line_idx, line in enumerate(lines):
        text = strip_adlibs(line.text.lower().strip())
        if not text:
            continue

        # Determine the first word's start time for this line (needed for clear timing)
        first_word_start = line.start
        if line.words:
            valid_words = [w for w in line.words if w.word.strip()]
            if valid_words:
                first_word_start = valid_words[0].start

        # Decide whether to clear before this line
        if line_idx > 0 and screen_text:
            prev_end = lines[line_idx - 1].end
            gap = line.start - prev_end

            # Check what screen would look like with this new line added
            test_text = screen_text + " " + text
            visual_lines = _estimate_brat_lines(test_text)

            should_clear = False
            # Clear on any noticeable pause (verse/section boundary)
            if gap > 0.8:
                should_clear = True
            # Clear if adding this line would exceed max visual lines
            elif visual_lines > MAX_VISUAL_LINES:
                should_clear = True
            # Clear if we already have 4+ lyric lines and there's a small gap
            elif line_count >= 4 and gap > 0.2:
                should_clear = True

            if should_clear:
                # Place clear 30ms before the first word, but at least 30ms
                # after the last typed char.
                clear_time = first_word_start - 0.03
                if events:
                    last_type_time = events[-1][0]
                    clear_time = max(clear_time, last_type_time + 0.03)

                if clear_time >= first_word_start:
                    if visual_lines > MAX_VISUAL_LINES:
                        # Gap too tight for a clean clear. Insert clear anyway —
                        # the post-processing pass will fix timing gaps.
                        if events:
                            clear_time = events[-1][0] + 0.03
                        else:
                            clear_time = first_word_start
                        events.append((clear_time, "clear", None))
                        screen_text = ""
                        line_count = 0
                    # else: gap too tight but not overflowing — skip clear
                else:
                    events.append((clear_time, "clear", None))
                    screen_text = ""
                    line_count = 0

        line_count += 1

        if line.words:
            # Use line text as source of truth, words only for timing.
            # Split the clean line text into words and pair with TimedWord timestamps.
            line_words = text.split()
            timed_words = [w for w in line.words if w.word.strip()]

            # Pair line_words with timed_words by position
            # If counts differ, distribute timing evenly for unmatched words
            for wi, display_word in enumerate(line_words):
                if wi < len(timed_words):
                    tw = timed_words[wi]
                    w_start = tw.start
                    w_end = tw.end
                else:
                    # More display words than timed words -- estimate from line timing
                    if timed_words:
                        w_start = timed_words[-1].end + 0.05
                        w_end = w_start + 0.2
                    else:
                        line_dur = max(line.end - line.start, 0.1)
                        word_dur = line_dur / max(len(line_words), 1)
                        w_start = line.start + wi * word_dur
                        w_end = w_start + word_dur

                # Space between words (skip if last event was a clear)
                if screen_text:
                    if events and events[-1][1] != "clear":
                        prev_time = events[-1][0]
                        gap_mid = (prev_time + w_start) / 2
                        sp_time = max(gap_mid, prev_time + 0.005)
                        events.append((sp_time, "type", " "))
                        screen_text += " "

                # Distribute chars across [w_start, w_end]
                n = len(display_word)
                w_dur = max(w_end - w_start, 0.03)
                for ci, ch in enumerate(display_word):
                    t = w_start + ci * (w_dur / max(n - 1, 1))
                    events.append((t, "type", ch))
                    screen_text += ch
        else:
            # Line-level fallback — distribute words evenly across line
            line_dur = max(line.end - line.start, 0.1)
            words = text.split()
            word_dur = line_dur / max(len(words), 1)
            for wi, w in enumerate(words):
                w_start = line.start + wi * word_dur
                w_end = w_start + word_dur

                # Space between words (skip if last event was a clear)
                if screen_text:
                    if events and events[-1][1] != "clear":
                        prev_time = events[-1][0]
                        sp_time = max((prev_time + w_start) / 2, prev_time + 0.005)
                        events.append((sp_time, "type", " "))
                        screen_text += " "

                n = len(w)
                for ci, ch in enumerate(w):
                    t = w_start + ci * (word_dur / max(n - 1, 1))
                    events.append((t, "type", ch))
                    screen_text += ch

    # Post-process: remove orphan sections (too few chars between clears).
    # If a section has fewer than 10 type events, remove the clear before it
    # so those chars join the next section instead of flashing briefly.
    events = _merge_orphan_sections(events)

    # Enforce minimum gaps around clears so every character renders into
    # at least 1 video frame before/after the wipe.
    # MIN_CLEAR_GAP of 50ms ≈ 1.5 frames at 30fps.
    MIN_CLEAR_GAP = 0.05
    for i in range(len(events)):
        t, action, char = events[i]
        if action != "clear":
            continue

        # Find the last type event before this clear
        prev_type_idx = None
        for j in range(i - 1, -1, -1):
            if events[j][1] == "type":
                prev_type_idx = j
                break

        # Find the first type event after this clear
        next_type_idx = None
        for j in range(i + 1, len(events)):
            if events[j][1] == "type":
                next_type_idx = j
                break

        # Ensure gap between last char and clear
        if prev_type_idx is not None:
            prev_t = events[prev_type_idx][0]
            if t - prev_t < MIN_CLEAR_GAP:
                # Shift clear later so last char has time to render
                events[i] = (prev_t + MIN_CLEAR_GAP, action, char)
                t = events[i][0]

        # Ensure gap between clear and next char
        if next_type_idx is not None:
            next_t = events[next_type_idx][0]
            if next_t - t < MIN_CLEAR_GAP:
                # Shift next char (and all subsequent chars in this line) later
                shift = MIN_CLEAR_GAP - (next_t - t)
                for j in range(next_type_idx, len(events)):
                    if events[j][1] == "clear":
                        break  # stop at next clear
                    jt, ja, jc = events[j]
                    events[j] = (jt + shift, ja, jc)

    # Remove any clears that ended up after their next type event (shouldn't happen now)
    safe_events = []
    for i, (t, action, char) in enumerate(events):
        if action == "clear":
            next_type_time = None
            for j in range(i + 1, len(events)):
                if events[j][1] == "type":
                    next_type_time = events[j][0]
                    break
            if next_type_time is not None and t > next_type_time:
                continue
        safe_events.append((t, action, char))
    events = safe_events

    return events


def _merge_orphan_sections(events):
    """Remove clears that would create tiny orphan sections (< 10 chars),
    but only if merging wouldn't cause screen overflow (> MAX_VISUAL_LINES).
    """
    if not events:
        return events

    MAX_VISUAL_LINES = 4

    # Find indices of all clear events
    clear_indices = [i for i, (_, action, _) in enumerate(events) if action == "clear"]
    if not clear_indices:
        return events

    # Check each section between clears
    removals = set()
    for ci_idx, ci in enumerate(clear_indices):
        # Count type events from this clear to the next clear (or end)
        next_clear = clear_indices[ci_idx + 1] if ci_idx + 1 < len(clear_indices) else len(events)
        type_count = sum(1 for j in range(ci + 1, next_clear) if events[j][1] == "type")
        if type_count < 10:
            # Check if removing this clear would overflow the screen
            # Simulate: collect text from previous clear (or start) to next_clear
            prev_clear = clear_indices[ci_idx - 1] if ci_idx > 0 else -1
            merged_text = ""
            for j in range(prev_clear + 1, next_clear):
                if j == ci:
                    continue  # skip the clear we're considering removing
                if events[j][1] == "type":
                    merged_text += events[j][2]
                elif events[j][1] == "clear":
                    merged_text = ""
            if _estimate_brat_lines(merged_text) <= MAX_VISUAL_LINES:
                removals.add(ci)

    if removals:
        events = [e for i, e in enumerate(events) if i not in removals]

    return events


async def record_brat_video(lines, audio_path, output_path, total_duration, audio_offset=0.0, sync_adjust=0.0, on_progress=None):
    """Open bratgenerator.com, type lyrics char-by-char, record screen.

    Two-phase approach:
    1. Setup phase (no recording): load page, switch to white, hide UI, verify ready
    2. Recording phase: new context with video recording, send all typing events
       to the browser in ONE call — browser schedules via setTimeout for ~4ms accuracy
    """
    from playwright.async_api import async_playwright

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    video_dir = str(TEMP_DIR / "brat_video")
    # Clean any leftover files from previous runs to avoid stale/corrupt webm
    if os.path.exists(video_dir):
        for f in os.listdir(video_dir):
            try:
                os.remove(os.path.join(video_dir, f))
            except Exception:
                pass
    os.makedirs(video_dir, exist_ok=True)

    events = _build_typing_events(lines, total_duration)
    print(f"       {len(events)} typing events over {total_duration:.1f}s")

    # Convert events to browser-scheduled format: [timeMs, action, char]
    # action: 0 = type, 1 = clear
    # Times are millisecond offsets from start + sync_adjust
    # Add START_BUFFER_MS so the first char doesn't fire at setTimeout(0)
    # which can be missed by the video encoder before it captures a frame.
    START_BUFFER_MS = 200
    browser_events = []
    for event_time, action, char in events:
        time_ms = max(0, round((event_time + sync_adjust) * 1000)) + START_BUFFER_MS
        if action == "clear":
            browser_events.append([time_ms, 1, ""])
        elif action == "type":
            browser_events.append([time_ms, 0, char])

    if browser_events:
        last_event_ms = browser_events[-1][0]
    else:
        last_event_ms = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # --- Phase 1: Setup (no recording) ---
        print("       Setting up bratgenerator.com...")
        setup_ctx = await browser.new_context(
            viewport={"width": 1080, "height": 1920},
        )
        setup_page = await setup_ctx.new_page()
        await setup_page.goto("https://www.bratgenerator.com", wait_until="networkidle")
        await setup_page.wait_for_timeout(1000)
        result = await setup_page.evaluate("""
            () => {
                if (typeof setupTheme === 'function') {
                    setupTheme('white');
                    return 'ok';
                }
                return 'setupTheme not found';
            }
        """)
        print(f"       Theme setup: {result}")
        await setup_ctx.close()

        # --- Phase 2: Recording ---
        print("       Starting recording...")
        rec_start = time.monotonic()
        rec_ctx = await browser.new_context(
            viewport={"width": 1080, "height": 1920},
            record_video_dir=video_dir,
            record_video_size={"width": 1080, "height": 1920},
        )
        page = await rec_ctx.new_page()
        await page.goto("https://www.bratgenerator.com", wait_until="networkidle")
        await page.wait_for_timeout(500)

        # Apply setup
        await page.evaluate(SETUP_JS)
        await page.wait_for_timeout(300)

        # Force CSS
        await page.add_style_tag(content="""
            body, html {
                background: white !important;
                overflow: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            .themeSelector, .header, .site-footer, h1, footer,
            header, #saveMessage, a[href*="howardstirling"],
            .node__content > *:not(:has(#memeContainer)) {
                display: none !important;
            }
            #memeContainer {
                width: 100vw !important;
                height: 100vh !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                z-index: 99999 !important;
                background-color: white !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            #textOverlay {
                max-width: 80% !important;
                width: 80% !important;
                height: 300px !important;
                position: relative !important;
                color: black !important;
            }
            #textInput {
                position: fixed !important;
                top: -9999px !important;
                opacity: 0 !important;
            }
        """)
        await page.wait_for_timeout(500)

        # Verify setup
        screenshot = await page.screenshot()
        img = Image.open(io.BytesIO(screenshot))
        pixel = img.getpixel((540, 960))
        if pixel[0] < 200:
            print(f"       WARNING: Center pixel is {pixel}, expected white.")
        else:
            print(f"       Setup verified (center pixel: {pixel})")

        await page.focus("#textInput")
        print(f"       Setup took {time.monotonic() - rec_start:.1f}s")

        if sync_adjust != 0:
            print(f"       Sync adjust: {sync_adjust:+.2f}s")

        # Measure setup_offset RIGHT before typing starts.
        # ADD START_BUFFER_MS so ffmpeg trims the extra blank time before the
        # first event fires. Browser events are delayed by START_BUFFER_MS,
        # so we must trim that much MORE to keep audio sync.
        setup_offset = time.monotonic() - rec_start + (START_BUFFER_MS / 1000.0)

        # --- Browser-scheduled typing ---
        # Send ALL events to browser in one call. Browser handles timing via setTimeout.
        # This gives ~4ms timing accuracy vs ~10-15ms with per-char evaluate().
        print(f"       Typing lyrics (browser-scheduled, {len(browser_events)} events)...")
        if on_progress:
            on_progress(5)

        await page.evaluate(SCHEDULE_TYPING_JS, browser_events)

        # Wait for all events to complete + hold end.
        # Extra 0.3s ensures the last character renders into a video frame
        # before we stop recording.
        wait_time = last_event_ms / 1000.0 + 0.8
        remaining_duration = total_duration - (last_event_ms / 1000.0)
        if remaining_duration > 0.8:
            wait_time = last_event_ms / 1000.0 + min(remaining_duration, 3.0)

        # Sleep in chunks to allow progress reporting
        sleep_start = time.monotonic()
        while True:
            elapsed = time.monotonic() - sleep_start
            if elapsed >= wait_time:
                break
            if on_progress:
                pct = max(5, min(95, int(elapsed / wait_time * 95)))
                on_progress(pct)
            await asyncio.sleep(min(2.0, wait_time - elapsed))

        # Final clear
        await page.evaluate(CLEAR_AND_REFOCUS_JS)
        await asyncio.sleep(0.5)

        if on_progress:
            on_progress(100)
        print(f"       Typing: 100%")

        # Close to finalize recording — Playwright flushes video on context close
        await rec_ctx.close()
        await asyncio.sleep(0.5)  # let video file finish writing to disk
        await browser.close()

    # Find recorded video
    video_files = [f for f in os.listdir(video_dir) if f.endswith(".webm")]
    if not video_files:
        raise RuntimeError("No video file recorded!")
    raw_video = os.path.join(video_dir, video_files[0])
    file_size = os.path.getsize(raw_video)
    print(f"       Raw recording: {raw_video} ({file_size // 1024}KB)")
    if file_size < 1024:
        raise RuntimeError(f"Video file too small ({file_size} bytes) — recording failed. "
                           "bratgenerator.com may not have loaded.")

    # Combine: trim setup_offset from video start, sync with audio
    print("       Combining video + audio with ffmpeg...")
    _combine_video_audio(raw_video, audio_path, str(output_path), total_duration, setup_offset, audio_offset)

    # Cleanup
    try:
        for f in os.listdir(video_dir):
            os.remove(os.path.join(video_dir, f))
        os.rmdir(video_dir)
    except Exception:
        pass

    return output_path


def _combine_video_audio(video_path, audio_path, output_path, duration, setup_offset=0, audio_offset=0):
    """Combine Playwright's webm recording with the song audio.
    Trims setup_offset from video start, audio_offset from audio start."""
    for encoder in ["h264_nvenc", "libx264"]:
        encoder_opts = ["-c:v", encoder]
        if encoder == "h264_nvenc":
            encoder_opts += ["-preset", "p4", "-cq", "23"]

        cmd = [
            "ffmpeg", "-y",
            "-accurate_seek",
            "-ss", str(setup_offset),  # Skip setup portion of video
            "-i", video_path,
            "-accurate_seek",
            "-ss", str(audio_offset),  # Skip to matching audio portion
            "-i", audio_path,
            "-t", str(duration),
            *encoder_opts,
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"       Encoded with {encoder}")
            return
        if encoder == "h264_nvenc":
            print("       GPU encode failed, trying CPU...")
            continue
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_brat.py <spotify_url>")
        sys.exit(1)

    spotify_url = sys.argv[1]
    # --test flag: only process first ~20 seconds
    test_mode = "--test" in sys.argv
    # --sync <seconds>: adjust typing timing (positive = type later, negative = earlier)
    sync_adjust = 0.0
    if "--sync" in sys.argv:
        idx = sys.argv.index("--sync")
        if idx + 1 < len(sys.argv):
            sync_adjust = float(sys.argv[idx + 1])

    # 1. Spotify metadata
    print("[1/4] Fetching Spotify metadata...")
    track_id = extract_track_id(spotify_url)
    meta = fetch_metadata(track_id)
    print(f"       {meta.title} by {', '.join(meta.artists)} ({meta.duration_ms // 1000}s)")

    # 2. Find or download audio
    print("[2/4] Looking for local audio...")
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    index = scan_library(LIBRARY_DIR)
    save_index(index, LIBRARY_DIR)
    match = match_track(meta, index)

    if match:
        audio_path = match.audio_path
        print(f"       Found: {audio_path}")
    else:
        print("       Not found locally. Downloading...")
        artist = meta.artists[0] if meta.artists else "Unknown"
        downloaded = download_track(spotify_url, artist, meta.title, duration_s=meta.duration_ms // 1000)
        if downloaded is None:
            print("ERROR: Download failed.")
            sys.exit(1)
        audio_path = str(downloaded)
        print(f"       Downloaded: {audio_path}")

    # 3. Lyrics
    print("[3/4] Getting lyrics...")
    use_alignment = "--no-align" not in sys.argv
    lines = get_lyrics(
        title=meta.title,
        artist=meta.artists[0] if meta.artists else "",
        duration_ms=meta.duration_ms,
        audio_path=audio_path,
        align=use_alignment,
    )
    if not lines:
        print("ERROR: No lyrics found.")
        sys.exit(1)

    # In test mode, pick a 20s window from the middle where there are lyrics
    if test_mode:
        # Find the densest 20s window
        best_start = 0.0
        best_count = 0
        for candidate in range(0, int(meta.duration_ms / 1000) - 20):
            count = sum(1 for l in lines if candidate <= l.start < candidate + 20)
            if count > best_count:
                best_count = count
                best_start = float(candidate)
        test_end = best_start + 20.0
        # Shift timestamps so the window starts at 0
        lines = [
            type(l)(text=l.text, start=l.start - best_start, end=l.end - best_start,
                    words=[type(w)(word=w.word, start=w.start - best_start, end=w.end - best_start)
                           for w in l.words] if l.words else None)
            for l in lines if best_start <= l.start < test_end
        ]
        total_duration = 20.0
        test_audio_offset = best_start
        print(f"       TEST MODE: {best_count} lines from {best_start:.0f}s-{test_end:.0f}s")
    else:
        total_duration = meta.duration_ms / 1000.0
        test_audio_offset = 0.0

    print(f"       {len(lines)} lyric lines")

    # 4. Record brat video
    print("[4/4] Recording brat-style video...")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    artist = meta.artists[0] if meta.artists else "Unknown"
    artist_tag = re.sub(r'[^a-zA-Z0-9]', '', artist).lower()
    safe_title = meta.title.replace("/", "-").replace("\\", "-")
    safe_artist = " & ".join(meta.artists).replace("/", "-").replace("\\", "-")
    suffix = "_test" if test_mode else ""
    safe_name = f"{safe_title} - {safe_artist} #musicvibes #lyricssong #slowedaudios #audios #{artist_tag}{suffix}"
    output_path = OUTPUTS_DIR / f"{safe_name}.mp4"

    asyncio.run(record_brat_video(lines, audio_path, output_path, total_duration, test_audio_offset, sync_adjust))

    print(f"\nDone! -> {output_path}")


if __name__ == "__main__":
    main()
