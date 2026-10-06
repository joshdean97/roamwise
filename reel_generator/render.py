"""Portable six-second renderer. All subprocesses use argument arrays."""
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT, DURATION = 1080, 1920, 6
DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def portable_text(text):
    # DejaVu has no colour emoji: preserve their meaning rather than draw boxes.
    def flag(match):
        return "[" + "".join(chr(ord(c) - 127397) for c in match[0]) + "]"
    text = re.sub("[\U0001f1e6-\U0001f1ff]{2}", flag, text)
    for icon, word in {"🚌": "Bus", "🚆": "Train", "✈️": "Flight", "✈": "Flight",
                       "⛴️": "Ferry", "🚗": "Car", "📍": ""}.items():
        text = text.replace(icon, word)
    return text


def wrapped_lines(text, font, draw, max_width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=font) > max_width:
                if line:
                    lines.append(line)
                    line = ""
                # Split long tokens so a URL or city name cannot escape the box.
                for character in word:
                    if draw.textlength(line + character, font=font) > max_width:
                        lines.append(line)
                        line = ""
                    line += character
            else:
                line = candidate
        lines.append(line)
    return lines


def overlay(text, path, font_path=DEFAULT_FONT):
    canvas = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(canvas)
    text = portable_text(text)
    if not text.strip() or len(text) > 5000:
        raise ValueError("Overlay must contain 1–5000 characters")
    for size in range(58, 31, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrapped_lines(text, font, draw, 860)
        line_height = int(size * 1.35)
        if len(lines) * line_height <= 1250:
            break
    else:
        raise ValueError("Text is too dense for the safe area; shorten it")
    # Keep the block clear of Instagram's top and bottom interface controls.
    y = 300 + (1250 - len(lines) * line_height) // 2
    shadow = Image.new("RGBA", canvas.size)
    shadow_draw = ImageDraw.Draw(shadow)
    for index, line in enumerate(lines):
        top = y + index * line_height
        shadow_draw.text((WIDTH // 2 + 2, top + 5), line, font=font,
                         anchor="mt", fill="black", stroke_width=5, stroke_fill="black")
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(7)))
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(lines):
        draw.text((WIDTH // 2, y + index * line_height), line, font=font,
                  anchor="mt", fill="white", stroke_width=3, stroke_fill="black")
    canvas.save(path)
    return {"font_size": size, "lines": len(lines)}


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=240)
    if result.returncode:
        # Do not include input URLs or credentials in logs.
        raise RuntimeError(f"{Path(args[0]).name} failed; check the local media file")
    return result.stdout


def probe(path):
    return json.loads(command(["ffprobe", "-v", "error", "-show_streams",
                               "-show_format", "-of", "json", str(path)]))


def validate(path):
    info = probe(path)
    streams = info["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    if (video["width"], video["height"]) != (WIDTH, HEIGHT):
        raise ValueError("Unexpected output dimensions")
    if abs(float(info["format"]["duration"]) - DURATION) > 0.15:
        raise ValueError("Unexpected output duration")
    if video["codec_name"] != "h264" or video["pix_fmt"] != "yuv420p":
        raise ValueError("Output is not mobile-compatible H.264")
    if any(s["codec_type"] == "audio" for s in streams):
        raise ValueError("Output must be silent")
    command(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])


def render(source, text, destination, font_path=DEFAULT_FONT):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if float(probe(source)["format"]["duration"]) < DURATION:
        raise ValueError("Source clip is shorter than six seconds")
    layer = destination.with_suffix(".overlay.png")
    layout = overlay(text, layer, font_path)
    temporary = destination.with_suffix(".tmp.mp4")
    command(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-loop", "1",
             "-i", str(layer), "-filter_complex_threads", "1", "-filter_complex",
             "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
             "crop=1080:1920,setsar=1,fps=30[base];[base][1:v]overlay=0:0:shortest=1[v]",
             "-map", "[v]", "-t", "6", "-an", "-c:v", "libx264", "-preset", "fast",
             "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "2", "-movflags",
             "+faststart", str(temporary)])
    validate(temporary)
    temporary.replace(destination)
    thumbnail = destination.with_suffix(".jpg")
    command(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(destination),
             "-frames:v", "1", str(thumbnail)])
    return layout
