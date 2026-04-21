from backend.models import TimedLine, TimedWord, TextBlock, FrameInstruction
from backend.config import FONT_PATH
from PIL import ImageFont

CANVAS_W = 1080
CANVAS_H = 1920
LEFT_MARGIN = 120
RIGHT_MARGIN = 80
USABLE_WIDTH = CANVAS_W - LEFT_MARGIN - RIGHT_MARGIN
VERTICAL_START = 640
VERTICAL_END = 1280
LINE_HEIGHT = 72
BASE_FONT_SIZE = 48
EMPHASIS_FONT_SIZE = 56
MAX_VISIBLE_LINES = 3

WORD_GAP_NORMAL = 0.4
WORD_GAP_NEWLINE = 1.2
LINE_GAP_CLEAR = 2.5
LINE_GAP_CLEAR_LINE_ONLY = 3.0
HELD_NOTE_THRESHOLD = 0.8

_layout_font_cache: dict[int, ImageFont.FreeTypeFont] = {}

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _layout_font_cache:
        _layout_font_cache[size] = ImageFont.truetype(str(FONT_PATH), size)
    return _layout_font_cache[size]

def _text_width(text: str, font_size: int) -> int:
    font = _get_font(font_size)
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]

def _word_wrap(text: str, font_size: int, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    wrapped = []
    current = words[0]
    for word in words[1:]:
        test = current + " " + word
        if _text_width(test, font_size) <= max_width:
            current = test
        else:
            wrapped.append(current)
            current = word
    wrapped.append(current)
    return wrapped

def generate_layout(lines: list[TimedLine], total_duration: float) -> list[FrameInstruction]:
    if not lines:
        return [FrameInstruction(time=0.0, duration=total_duration, blocks=[], transition="cut")]
    has_word_level = any(line.words for line in lines)
    if has_word_level:
        return _layout_word_level(lines, total_duration)
    else:
        return _layout_line_level(lines, total_duration)

def _layout_line_level(lines: list[TimedLine], total_duration: float) -> list[FrameInstruction]:
    frames: list[FrameInstruction] = []
    visible_lines: list[tuple[str, float]] = []
    indent_toggle = False

    if lines[0].start > 0.1:
        frames.append(FrameInstruction(time=0.0, duration=lines[0].start, blocks=[], transition="cut"))

    for i, line in enumerate(lines):
        text = line.text.lower().strip()
        if not text:
            continue

        if visible_lines:
            last_end = lines[i - 1].end if i > 0 else 0
            gap = line.start - last_end
            if gap > LINE_GAP_CLEAR_LINE_ONLY or len(visible_lines) >= MAX_VISIBLE_LINES:
                if frames:
                    frames.append(FrameInstruction(
                        time=last_end, duration=min(0.3, gap * 0.5),
                        blocks=[], transition="fade_out",
                    ))
                visible_lines = []

        visible_lines.append((text, line.start))

        blocks = []
        y = VERTICAL_START
        for vis_text, _ in visible_lines:
            word_count = len(vis_text.split())
            x = LEFT_MARGIN
            if word_count <= 3 and indent_toggle:
                x += 40
            indent_toggle = not indent_toggle
            wrapped = _word_wrap(vis_text, BASE_FONT_SIZE, USABLE_WIDTH)
            for wrap_line in wrapped:
                blocks.append(TextBlock(text=wrap_line, x=x, y=y, font_size=BASE_FONT_SIZE, opacity=255))
                y += LINE_HEIGHT

        if i + 1 < len(lines):
            duration = lines[i + 1].start - line.start
        else:
            duration = line.end - line.start

        frames.append(FrameInstruction(
            time=line.start, duration=max(duration, 0.033), blocks=blocks, transition="fade_in",
        ))

    last_end = lines[-1].end
    if last_end < total_duration:
        frames.append(FrameInstruction(
            time=last_end, duration=total_duration - last_end, blocks=[], transition="fade_out",
        ))
    return frames

def _layout_word_level(lines: list[TimedLine], total_duration: float) -> list[FrameInstruction]:
    frames: list[FrameInstruction] = []
    all_words: list[TimedWord] = []
    for line in lines:
        if line.words:
            all_words.extend(line.words)
    if not all_words:
        return _layout_line_level(lines, total_duration)

    if all_words[0].start > 0.1:
        frames.append(FrameInstruction(time=0.0, duration=all_words[0].start, blocks=[], transition="cut"))

    phrases: list[list[TimedWord]] = []
    current_phrase: list[TimedWord] = [all_words[0]]
    for i in range(1, len(all_words)):
        gap = all_words[i].start - all_words[i - 1].end
        if gap > LINE_GAP_CLEAR:
            phrases.append(current_phrase)
            current_phrase = [all_words[i]]
        else:
            current_phrase.append(all_words[i])
    phrases.append(current_phrase)

    for phrase_words in phrases:
        if frames and frames[-1].blocks:
            prev_end = frames[-1].time + frames[-1].duration
            gap_to_phrase = phrase_words[0].start - prev_end
            if gap_to_phrase > 0.1:
                frames.append(FrameInstruction(
                    time=prev_end, duration=min(0.3, gap_to_phrase),
                    blocks=[], transition="fade_out",
                ))

        for word_idx in range(len(phrase_words)):
            visible_words = phrase_words[:word_idx + 1]
            current_word = phrase_words[word_idx]

            visual_lines: list[list[tuple[str, int, int]]] = []
            current_line: list[tuple[str, int, int]] = []
            current_line_width = 0

            for j, word in enumerate(visible_words):
                word_text = word.word.lower().strip()
                if not word_text:
                    continue
                word_duration = word.end - word.start
                font_size = EMPHASIS_FONT_SIZE if word_duration > HELD_NOTE_THRESHOLD else BASE_FONT_SIZE
                w_width = _text_width(word_text, font_size)

                extra_space = 0
                if j > 0 and current_line:
                    gap = word.start - visible_words[j - 1].end
                    if gap > WORD_GAP_NEWLINE:
                        visual_lines.append(current_line)
                        current_line = []
                        current_line_width = 0
                    elif gap > WORD_GAP_NORMAL:
                        extra_space = int(16 + (gap - WORD_GAP_NORMAL) * 80)

                space_needed = (extra_space if current_line else 0) + w_width + 16
                if current_line and current_line_width + space_needed > USABLE_WIDTH:
                    visual_lines.append(current_line)
                    current_line = []
                    current_line_width = 0
                    extra_space = 0

                current_line.append((word_text, extra_space, font_size))
                current_line_width += (extra_space if len(current_line) > 1 else 0) + w_width + 16

            if current_line:
                visual_lines.append(current_line)

            blocks = []
            y = VERTICAL_START
            for vline in visual_lines[:MAX_VISIBLE_LINES]:
                x = LEFT_MARGIN
                for k, (word_text, extra_space, font_size) in enumerate(vline):
                    if k > 0:
                        x += extra_space if extra_space > 0 else 16
                    blocks.append(TextBlock(text=word_text, x=x, y=y, font_size=font_size, opacity=255))
                    x += _text_width(word_text, font_size)
                y += LINE_HEIGHT

            if word_idx + 1 < len(phrase_words):
                duration = phrase_words[word_idx + 1].start - current_word.start
            else:
                duration = current_word.end - current_word.start

            transition = "fade_in" if word_idx == 0 else "cut"
            frames.append(FrameInstruction(
                time=current_word.start, duration=max(duration, 0.033), blocks=blocks, transition=transition,
            ))

    if all_words:
        last_end = all_words[-1].end
        if last_end < total_duration:
            frames.append(FrameInstruction(
                time=last_end, duration=total_duration - last_end, blocks=[], transition="fade_out",
            ))
    return frames
