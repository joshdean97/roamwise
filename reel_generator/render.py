"""Portable six-second renderer. All subprocesses use argument arrays."""
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT, DURATION = 1080, 1920, 6
DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
# Keep flags, variation selectors, skin tones and joined emoji together.
_ICON = r"[\U0001f300-\U0001faff\u2600-\u27bf](?:\ufe0f|\ufe0e)?[\U0001f3fb-\U0001f3ff]?"
EMOJI = re.compile(r"[\U0001f1e6-\U0001f1ff]{2}|[0-9#*]\ufe0f?\u20e3|" + _ICON + r"(?:\u200d" + _ICON + r")*")


def portable_text(text):
    # Preserve the API's copy; the overlay uses a separate colour emoji font.
    return text


def text_runs(text):
    start = 0
    for match in EMOJI.finditer(text):
        if start < match.start():
            yield text[start:match.start()], False
        yield match[0], True
        start = match.end()
    if start < len(text):
        yield text[start:], False


@lru_cache(maxsize=256)
def emoji_tile(icon, size):
    # Noto's bitmap font has a fixed 109 px strike. Resize the rendered glyph,
    # rather than asking FreeType for an unsupported font size.
    font = ImageFont.truetype(EMOJI_FONT, 109)
    box = font.getbbox(icon)
    tile = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]))
    ImageDraw.Draw(tile).text((-box[0], -box[1]), icon, font=font, embedded_color=True)
    bounds = tile.getbbox()
    if not bounds:
        raise ValueError("Emoji font could not render an overlay icon")
    tile = tile.crop(bounds)
    tile.thumbnail((size, size), Image.Resampling.LANCZOS)
    return tile


def mixed_width(text, font, draw):
    return sum(font.size * 1.15 if is_emoji else draw.textlength(run, font=font)
               for run, is_emoji in text_runs(text))


def wrapped_lines(text, font, draw, max_width, measure=None):
    measure = measure or (lambda value: draw.textlength(value, font=font))
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if measure(candidate) > max_width:
                if line:
                    lines.append(line)
                    line = ""
                # Split long tokens so a URL or city name cannot escape the box.
                for run, is_emoji in text_runs(word):
                    for character in [run] if is_emoji else run:
                        if measure(line + character) > max_width:
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
        lines = wrapped_lines(text, font, draw, 860, lambda value: mixed_width(value, font, draw))
        line_height = int(size * 1.35)
        if len(lines) * line_height <= 1250:
            break
    else:
        raise ValueError("Text is too dense for the safe area; shorten it")
    # Keep the block clear of Instagram's top and bottom interface controls.
    y = 300 + (1250 - len(lines) * line_height) // 2
    shadow = Image.new("RGBA", canvas.size)
    foreground = Image.new("RGBA", canvas.size)
    foreground_draw = ImageDraw.Draw(foreground)
    shadow_draw = ImageDraw.Draw(shadow)
    for index, line in enumerate(lines):
        top = y + index * line_height
        x = (WIDTH - mixed_width(line, font, draw)) / 2
        baseline = top + size
        for run, is_emoji in text_runs(line):
            if is_emoji:
                tile = emoji_tile(run, size)
                cell = size * 1.15
                left = round(x + (cell - tile.width) / 2)
                cap_height = -font.getbbox("M", anchor="ls")[1]
                foreground.alpha_composite(tile, (left, round(baseline - (cap_height + tile.height) / 2)))
                x += cell
            else:
                shadow_draw.text((x + 2, baseline + 5), run, font=font,
                                 anchor="ls", fill="black", stroke_width=5, stroke_fill="black")
                foreground_draw.text((x, baseline), run, font=font,
                                     anchor="ls", fill="white", stroke_width=3, stroke_fill="black")
                x += draw.textlength(run, font=font)
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(7)))
    canvas = Image.alpha_composite(canvas, foreground)
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
