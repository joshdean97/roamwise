import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from reel_generator.__main__ import build_payload, render_id, run, validate_queue_response
from reel_generator.render import overlay, portable_text, wrapped_lines
from reel_generator.services import ObjectStorage, failure_detail, select_clips
from PIL import Image, ImageDraw, ImageFont


def test_public_media_check_uses_cloudflare_compatible_user_agent(tmp_path):
    from unittest.mock import Mock
    storage = ObjectStorage.__new__(ObjectStorage)
    storage.client = Mock()
    storage.bucket = "test-bucket"
    storage.public_url = "https://public.example"
    response = Mock()
    response.__enter__ = Mock(return_value=SimpleNamespace(status=200))
    response.__exit__ = Mock(return_value=False)
    with patch("reel_generator.services.urlopen", return_value=response) as open_url:
        assert storage.upload(tmp_path / "reel.mp4", "reels/test.mp4") == "https://public.example/reels/test.mp4"
    request = open_url.call_args.args[0]
    assert request.get_method() == "HEAD"
    assert request.get_header("User-agent") == "LeavePrints-Reels/1"


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


def test_numeric_and_wrapped_client_errors_have_http_status():
    from boto3.exceptions import S3UploadFailedError
    from botocore.exceptions import ClientError
    numeric = S3UploadFailedError("private-key: An error occurred (403) when calling PutObject")
    assert "HTTP 403" in failure_detail(numeric)
    assert "private-key" not in failure_detail(numeric)
    inner = ClientError({"Error": {"Code": "Unrecognised", "Message": "private-key"},
                         "ResponseMetadata": {"HTTPStatusCode": 501}}, "PutObject")
    wrapper = S3UploadFailedError("sensitive wrapper message")
    wrapper.__context__ = inner
    assert "HTTP 501" in failure_detail(wrapper)
    assert "private-key" not in failure_detail(wrapper)


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


def test_emoji_are_preserved_and_rendered_in_colour(tmp_path):
    from reel_generator.render import emoji_tile, text_runs
    text = "🇬🇧 London 🚆 Paris ✈️ Rome 🇦🇱"
    assert portable_text(text) == text
    assert [run for run, icon in text_runs(text) if icon] == ["🇬🇧", "🚆", "✈️", "🇦🇱"]
    for icon in ("🇦🇱", "🚌", "✈️", "👩🏽‍💻"):
        tile = emoji_tile(icon, 50)
        assert tile.getbbox()
        assert any(r != g or g != b for r, g, b, a in tile.get_flattened_data() if a > 200)
    overlay(text, tmp_path / "emoji.png")


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


def test_fresh_generations_have_distinct_ids_but_retries_are_stable():
    first = render_id(7, 1, "99", "text", "batch-a")
    assert first == render_id(7, 1, "99", "text", "batch-a")
    assert first != render_id(7, 1, "99", "text", "batch-b")
    assert first != render_id(7, 1, "99", "text")


def test_repeated_trip_and_clips_create_distinct_fresh_batches(tmp_path):
    trip = {"id": 7, "destinations": [{"city": c} for c in ("A", "B", "C")],
            "reel": {"headline": "Test", "caption": "Caption", "overlay_text": "Hook\nText"}}
    trip_file = tmp_path / "trip.json"
    trip_file.write_text(json.dumps(trip))
    clips = tmp_path / "clips"
    clips.mkdir()
    for i in range(6):
        (clips / f"{i}.mp4").write_bytes(b"source")

    def fake_render(source, text, destination, font):
        destination.write_bytes(b"encoded")
        destination.with_suffix(".jpg").write_bytes(b"thumbnail")
        return {"font_size": 40}

    batches = []
    with patch("reel_generator.__main__.render", side_effect=fake_render):
        for name in ("first", "second"):
            output = tmp_path / name
            run(SimpleNamespace(output=str(output), trip_file=str(trip_file), publish=False,
                                clips_dir=str(clips), font="unused"))
            batches.append(json.loads((output / "batch.json").read_text()))
    assert batches[0]["generation_id"] != batches[1]["generation_id"]
    assert {r["render_id"] for r in batches[0]["renders"].values()}.isdisjoint(
        r["render_id"] for r in batches[1]["renders"].values())


@pytest.mark.parametrize("status,created", [("ready", True), ("approved", False), ("posted", False)])
def test_queue_confirmation_accepts_new_or_existing_active_drafts(status, created):
    payload = {"trip_id": 7, "renders": [{"render_id": str(i)} for i in range(6)]}
    response = {"draft_batch": {"trip_id": 7, "count": 6, "batch_key": "key", "created": created,
                "drafts": [{"render_id": str(i), "status": status} for i in range(6)]}}
    assert validate_queue_response(payload, response)["created"] is created


@pytest.mark.parametrize("status", ["rejected", "unknown"])
def test_rejected_duplicate_batch_is_not_reported_as_queued(tmp_path, status):
    trip = {"id": 7, "reel": {"headline": "Test", "caption": "Caption", "overlay_text": "Text"}}
    clips = [{"id": str(i), "city": "Test", "page_url": "", "attribution": "Test"} for i in range(6)]
    batch = {"trip": trip, "generation_id": "persisted", "clips": clips, "renders": {}, "queued": False}
    (tmp_path / "batch.json").write_text(json.dumps(batch))
    for i in range(1, 7):
        (tmp_path / f"reel-{i:02d}.mp4").write_bytes(b"encoded")
        (tmp_path / f"reel-{i:02d}.jpg").write_bytes(b"thumbnail")
    args = SimpleNamespace(output=str(tmp_path), trip_file=None, publish=True, clips_dir=None)

    def duplicate_response(payload):
        return {"draft_batch": {"trip_id": 7, "count": 6, "batch_key": "old", "created": False,
                "drafts": [{"render_id": r["render_id"], "status": status} for r in payload["renders"]]}}

    with patch("reel_generator.__main__.ObjectStorage") as storage, \
            patch("reel_generator.__main__.ContentAPI") as api, \
            patch("reel_generator.__main__.validate"):
        storage.return_value.upload.return_value = "https://cdn.example/media"
        api.return_value.save.side_effect = duplicate_response
        with pytest.raises(RuntimeError, match="rejected or inactive"):
            run(args)
    assert not json.loads((tmp_path / "batch.json").read_text())["queued"]
    assert not (tmp_path / "summary.json").exists()


def test_queue_confirmation_rejects_wrong_or_partial_drafts():
    payload = {"trip_id": 7, "renders": [{"render_id": str(i)} for i in range(6)]}
    for count, ids, trip_id in [(5, range(5), 7), (6, range(1, 7), 7), (6, range(6), 8)]:
        response = {"draft_batch": {"trip_id": trip_id, "count": count, "batch_key": "key", "created": True,
                    "drafts": [{"render_id": str(i), "status": "ready"} for i in ids]}}
        with pytest.raises(RuntimeError, match="all six"):
            validate_queue_response(payload, response)


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
    generation_id = batch["generation_id"]
    completed_id = batch["renders"]["1"]["render_id"]
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
    recovered = json.loads((output / "batch.json").read_text())
    assert recovered["generation_id"] == generation_id
    assert recovered["renders"]["1"]["render_id"] == completed_id
