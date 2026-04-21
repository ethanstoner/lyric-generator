import shutil
import subprocess
from typing import Callable
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from backend.models import FrameInstruction, TextBlock
from backend.config import FONT_PATH, TEMP_DIR, OUTPUTS_DIR

CANVAS_W = 1080
CANVAS_H = 1920
BG_COLOR = (255, 255, 255)
FPS = 30

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(str(FONT_PATH), size)
    return _font_cache[size]

def render_frame(instruction: FrameInstruction, output_path: Path, opacity_override: int | None = None):
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    if instruction.blocks:
        overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        for block in instruction.blocks:
            font = _get_font(block.font_size)
            opacity = opacity_override if opacity_override is not None else block.opacity
            color = (0, 0, 0, opacity)
            draw.text((block.x, block.y), block.text, font=font, fill=color)
        bg_rgba = img.convert("RGBA")
        composited = Image.alpha_composite(bg_rgba, overlay)
        img = composited.convert("RGB")
    img.save(str(output_path), "PNG")

def _generate_transition_frames(instruction, frame_dir, frame_counter):
    entries = []
    transition = instruction.transition

    if transition == "fade_in" and instruction.blocks:
        n_frames = 4
        frame_duration = 1.0 / FPS
        for i in range(n_frames):
            opacity = int(255 * (i + 1) / n_frames)
            frame_path = frame_dir / f"frame_{frame_counter:05d}.png"
            render_frame(instruction, frame_path, opacity_override=opacity)
            entries.append((f"frame_{frame_counter:05d}.png", frame_duration))
            frame_counter += 1
        hold_duration = instruction.duration - (n_frames * frame_duration)
        if hold_duration > 0:
            frame_path = frame_dir / f"frame_{frame_counter:05d}.png"
            render_frame(instruction, frame_path)
            entries.append((f"frame_{frame_counter:05d}.png", hold_duration))
            frame_counter += 1

    elif transition == "fade_out":
        fade_time_used = 0.0
        if instruction.blocks:
            n_frames = 9
            frame_duration = 1.0 / FPS
            fade_time_used = n_frames * frame_duration
            for i in range(n_frames):
                opacity = int(255 * (1 - (i + 1) / n_frames))
                frame_path = frame_dir / f"frame_{frame_counter:05d}.png"
                render_frame(instruction, frame_path, opacity_override=max(opacity, 0))
                entries.append((f"frame_{frame_counter:05d}.png", frame_duration))
                frame_counter += 1
        hold_duration = instruction.duration - fade_time_used
        if hold_duration > 0:
            frame_path = frame_dir / f"frame_{frame_counter:05d}.png"
            blank = FrameInstruction(time=0, duration=0, blocks=[], transition="cut")
            render_frame(blank, frame_path)
            entries.append((f"frame_{frame_counter:05d}.png", hold_duration))
            frame_counter += 1

    else:  # "cut"
        frame_path = frame_dir / f"frame_{frame_counter:05d}.png"
        render_frame(instruction, frame_path)
        entries.append((f"frame_{frame_counter:05d}.png", instruction.duration))
        frame_counter += 1

    return entries, frame_counter

def render_video(frames: list[FrameInstruction], audio_path: str, job_id: str,
                 on_progress: Callable[[int], None] | None = None) -> Path:
    frame_dir = TEMP_DIR / job_id
    frame_dir.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUTS_DIR / f"{job_id}.mp4"

    try:
        concat_entries: list[tuple[str, float]] = []
        frame_counter = 0
        total = len(frames)

        for i, instruction in enumerate(frames):
            entries, frame_counter = _generate_transition_frames(instruction, frame_dir, frame_counter)
            concat_entries.extend(entries)
            if on_progress:
                on_progress(int((i + 1) / total * 80))

        concat_path = frame_dir / "concat.txt"
        with open(concat_path, "w") as f:
            for filename, duration in concat_entries:
                f.write(f"file '{filename}'\n")
                f.write(f"duration {duration:.6f}\n")
            if concat_entries:
                f.write(f"file '{concat_entries[-1][0]}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-i", audio_path,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")
        if on_progress:
            on_progress(100)
        return output_path
    finally:
        if frame_dir.exists():
            shutil.rmtree(frame_dir, ignore_errors=True)
