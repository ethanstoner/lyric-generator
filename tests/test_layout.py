import pytest
from backend.services.layout import generate_layout
from backend.models import TimedLine, TimedWord, FrameInstruction

def test_layout_line_level_basic():
    lines = [
        TimedLine(text="hello world", start=1.0, end=3.0, words=None),
        TimedLine(text="second line", start=3.5, end=5.0, words=None),
    ]
    frames = generate_layout(lines, total_duration=10.0)
    assert len(frames) > 0
    assert all(isinstance(f, FrameInstruction) for f in frames)
    assert any("hello world" in b.text for f in frames for b in f.blocks)

def test_layout_word_level_spacing():
    words = [
        TimedWord(word="so", start=1.0, end=1.3),
        TimedWord(word="emotional", start=1.8, end=2.5),
    ]
    lines = [TimedLine(text="so emotional", start=1.0, end=2.5, words=words)]
    frames = generate_layout(lines, total_duration=5.0)
    assert len(frames) > 0

def test_layout_screen_clear_on_long_gap():
    lines = [
        TimedLine(text="first", start=1.0, end=2.0, words=None),
        TimedLine(text="second", start=6.0, end=7.0, words=None),
    ]
    frames = generate_layout(lines, total_duration=10.0)
    transitions = [f.transition for f in frames]
    assert "fade_out" in transitions

def test_layout_lowercase():
    lines = [TimedLine(text="HELLO WORLD", start=1.0, end=3.0, words=None)]
    frames = generate_layout(lines, total_duration=5.0)
    for frame in frames:
        for block in frame.blocks:
            assert block.text == block.text.lower()

def test_layout_empty_lines():
    frames = generate_layout([], total_duration=5.0)
    assert len(frames) >= 1

def test_layout_text_within_canvas():
    lines = [
        TimedLine(text="a line of text", start=1.0, end=3.0, words=None),
        TimedLine(text="another line here", start=3.5, end=5.0, words=None),
    ]
    frames = generate_layout(lines, total_duration=8.0)
    for frame in frames:
        for block in frame.blocks:
            assert 0 <= block.x <= 1080
            assert 0 <= block.y <= 1920
