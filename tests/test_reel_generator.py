import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from reel_generator.__main__ import build_payload, render_id, run
from reel_generator.render import overlay, portable_text, wrapped_lines
from reel_generator.services import failure_detail, select_clips
from PIL import Image, ImageDraw, ImageFont


def test_storage_diagnostics_do_not_expose_raw_credentials():
    from boto3.exceptions import S3UploadFailedError
    from urllib.error import HTTPError
    for code in ("AccessDenied", "SignatureDoesNotMatch", "InvalidAccessKeyId", "NoSuchBucket"):
        error = S3UploadFailedError(f"sensitive-key: An error occurred ({code}) when calling PutObject")
        detail = failure_detail(error)
        assert code in detail
        assert "sensitive-key" not in detail
    assert "HTTP 403" in failure_detail(HTTPError("https://secret.example", 403, "Forbidden", {}, None))
    assert "secret" not in failure_detail(HTTPError("https://secret.example", 403, "Forbidden", {}, None))


def video(identifier, duration=10, width=1080, height=1920):
    return {"id": identifier, "duration": duration, "url": f"https://www.pexels.com/video/{identifier}",
            "user": {"name": "Test creator"}, "video_files": [{"file_type": "video/mp4",
            "width": width, "height": height, "link": f"https://videos.pexels.com/{identifier}.mp4"}]}


def test_clip_selection_excludes_short_landscape_and_duplicates():
    clips = select_clips([video(1, duration=3), video(2, width=1920, height=1080),
                          video(3), video(4), video(5)], exclude={"3"})
    assert [c["id"] for c in clips] == ["4", "5"]
    with pytest.raises(ValueError):
        select_clips([video(1, duration=3)])


def test_emoji_have_portable_meaning():
    assert portable_text("🇬🇧 London 🚆 Paris ✈️ Rome") == "[GB] London Train Paris Flight Rome"


def test_long_word_wrap_and_layout_safety(tmp_path):
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 50)
    draw = ImageDraw.Draw(Image.new("RGBA", (1080, 1920)))
    assert all(draw.textlength(line, font=font) <= 860
               for line in wrapped_lines("x" * 200, font, draw, 860))
    overlay("I made a website…\nParis — £200\nLink in bio", tmp_path / "overlay.png")
    box = Image.open(tmp_path / "overlay.png").getbbox()
    assert box[0] > 60 and box[2] < 1020 and box[1] > 250 and box[3] < 1600
    with pytest.raises(ValueError):
        overlay("too much text\n" * 300, tmp_path / "overflow.png")


def test_stable_ids_and_partial_queue_gate():
    assert render_id(7, 1, "99", "text") == render_id(7, 1, "99", "text")
    assert render_id(7, 1, "99", "text") != render_id(7, 1, "99", "changed")
    with pytest.raises(ValueError):
        build_payload({}, [{"render_status": "succeeded"}] * 5)


def test_already_queued_batch_does_not_request_new_trip(tmp_path):
    (tmp_path / "batch.json").write_text(json.dumps({"queued": True, "trip": {"id": 7}}))
    args = SimpleNamespace(output=str(tmp_path), trip_file=None, publish=True, clips_dir=None)
    with patch("reel_generator.__main__.ObjectStorage"), patch("reel_generator.__main__.ContentAPI") as api:
        run(args)
    api.return_value.trips.assert_not_called()
    api.return_value.save.assert_not_called()


def test_interrupted_batch_preserves_completed_reels_and_resumes(tmp_path):
    trip = {"id": 7, "destinations": [{"city": c, "country": "Test"} for c in ("A", "B", "C")],
            "reel": {"headline": "Test", "caption": "Test caption", "overlay_text": "Hook\nCosts\nCTA"}}
    trip_file = tmp_path / "trip.json"
    trip_file.write_text(json.dumps(trip))
    source_dir = tmp_path / "clips"
    source_dir.mkdir()
    for i in range(6):
        (source_dir / f"{i}.mp4").write_bytes(b"source")
    output = tmp_path / "output"
    args = SimpleNamespace(output=str(output), trip_file=str(trip_file), publish=False,
                           clips_dir=str(source_dir), font="unused")

    def fake_render(source, text, destination, font):
        if destination.name == "reel-03.mp4":
            raise RuntimeError("Temporary encode failure")
        destination.write_bytes(b"encoded")
        destination.with_suffix(".jpg").write_bytes(b"thumbnail")
        return {"font_size": 40}

    with patch("reel_generator.__main__.render", side_effect=fake_render), patch("reel_generator.__main__.validate"):
        with pytest.raises(RuntimeError, match="failed positions: \\[3\\]"):
            run(args)
    batch = json.loads((output / "batch.json").read_text())
    assert len(batch["renders"]) == 5
    assert not batch["queued"]

    def recovered_render(source, text, destination, font):
        destination.write_bytes(b"encoded")
        destination.with_suffix(".jpg").write_bytes(b"thumbnail")
        return {"font_size": 40}

    with patch("reel_generator.__main__.render", side_effect=recovered_render) as renderer, \
            patch("reel_generator.__main__.validate"):
        run(args)
    assert renderer.call_count == 1
    assert len(json.loads((output / "batch.json").read_text())["renders"]) == 6
