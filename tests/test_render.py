import pytest
from pathlib import Path
from backend.services.render import render_frame
from backend.models import TextBlock, FrameInstruction

def test_render_frame_blank(tmp_path):
    fi = FrameInstruction(time=0.0, duration=1.0, blocks=[], transition="cut")
    out_path = tmp_path / "frame.png"
    render_frame(fi, out_path)
    assert out_path.exists()
    assert out_path.stat().st_size > 0

def test_render_frame_with_text(tmp_path):
    blocks = [
        TextBlock(text="hello world", x=120, y=640, font_size=48, opacity=255),
        TextBlock(text="test", x=120, y=712, font_size=48, opacity=128),
    ]
    fi = FrameInstruction(time=0.0, duration=1.0, blocks=blocks, transition="cut")
    out_path = tmp_path / "frame.png"
    render_frame(fi, out_path)
    assert out_path.exists()
    assert out_path.stat().st_size > 1000

def test_render_frame_dimensions(tmp_path):
    from PIL import Image
    fi = FrameInstruction(time=0.0, duration=1.0, blocks=[], transition="cut")
    out_path = tmp_path / "frame.png"
    render_frame(fi, out_path)
    img = Image.open(out_path)
    assert img.size == (1080, 1920)
