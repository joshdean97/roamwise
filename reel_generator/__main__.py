import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .render import DEFAULT_FONT, command, render, validate
from .services import ContentAPI, ObjectStorage, download, failure_detail, search_clips


def write_json(path, data):
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def render_id(trip_id, position, clip_id, overlay_text, generation_id=""):
    fingerprint = hashlib.sha256(overlay_text.encode()).hexdigest()[:16]
    identifier = f"ffmpeg-v1-{trip_id}-{position}-{clip_id}-{fingerprint}"
    return f"{identifier}-{generation_id}" if generation_id else identifier


def validate_queue_response(payload, response):
    """An idempotent API response may refer to a rejected historical batch."""
    batch = response.get("draft_batch") if isinstance(response, dict) else None
    if not isinstance(batch, dict):
        raise RuntimeError("Queue API did not confirm a draft batch")
    drafts = batch.get("drafts")
    expected_ids = {render["render_id"] for render in payload["renders"]}
    if (batch.get("trip_id") != payload["trip_id"] or batch.get("count") != 6
            or not batch.get("batch_key") or not isinstance(drafts, list)
            or len(drafts) != 6 or any(not isinstance(draft, dict) for draft in drafts)
            or {draft.get("render_id") for draft in drafts} != expected_ids
            or not isinstance(batch.get("created"), bool)):
        raise RuntimeError("Queue API did not confirm all six submitted drafts")
    if any(draft.get("status") not in {"ready", "approved", "posted"} for draft in drafts):
        raise RuntimeError("Queue API returned rejected or inactive drafts; no new review batch was saved")
    return batch


def build_payload(trip, renders):
    if len(renders) != 6 or any(r.get("render_status") != "succeeded" for r in renders):
        raise ValueError("Only six successfully rendered and uploaded reels can enter the queue")
    return {"trip_id": trip["id"], "platform": "instagram", "format": "trial_reel",
            "headline": trip["reel"]["headline"], "caption": trip["reel"]["caption"],
            "overlay_text": trip["reel"]["overlay_text"], "renders": renders}


def run(args):
    started = time.monotonic()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    batch_path = output / "batch.json"
    # Validate production configuration before doing any rendering work.
    storage = ObjectStorage() if args.publish else None
    api = ContentAPI() if args.publish or not args.trip_file else None
    if batch_path.exists():
        batch = json.loads(batch_path.read_text())
        if args.trip_file and batch["trip"]["id"] != json.loads(Path(args.trip_file).read_text())["id"]:
            raise ValueError("Output directory already belongs to another trip")
        if batch.get("queued"):
            print("This batch is already in the review queue; nothing to regenerate")
            return
    else:
        if args.trip_file:
            trip = json.loads(Path(args.trip_file).read_text())
        else:
            candidates = api.trips()
            trip = next((t for t in candidates if len(t["destinations"]) >= 3), None)
            if not trip:
                print("No eligible unused three-city trip; no batch generated")
                return
        if len(trip["destinations"]) < 3:
            raise ValueError("This format requires at least three destinations")
        # Hook can be adjusted locally without changing the application's API.
        original = trip["reel"]["overlay_text"]
        trip["reel"]["overlay_text"] = "I made a website to budget trips…" + "\n" + original.partition("\n")[2]
        # Fresh generations are distinct; the persisted namespace keeps retries
        # idempotent. Legacy artifacts retain their original IDs when resumed.
        batch = {"version": 1, "generation_id": uuid.uuid4().hex,
                 "trip": trip, "clips": [], "renders": {}, "queued": False}
        write_json(batch_path, batch)

    trip = batch["trip"]
    local_sources = sorted(Path(args.clips_dir).glob("*.mp4")) if args.clips_dir else []
    if args.clips_dir and len(local_sources) != 6:
        raise ValueError("Local mode requires exactly six MP4 files")
    # Persist each city's selection before the next request; retries reuse the same clips.
    for index in range(len(batch["clips"]) // 2, 3):
        city = trip["destinations"][index]
        if local_sources:
            clips = [{"id": f"local-{index * 2 + j + 1}", "local_path": str(local_sources[index * 2 + j].resolve()),
                      "page_url": "", "attribution": "Local test footage"} for j in range(2)]
        else:
            clips = search_clips(city, {c["id"] for c in batch["clips"]})
        batch["clips"].extend({**clip, "city": city["city"]} for clip in clips)
        write_json(batch_path, batch)

    failures = []
    for position, clip in enumerate(batch["clips"], 1):
        name = f"reel-{position:02d}"
        destination = output / (name + ".mp4")
        try:
            if destination.exists():
                try:
                    validate(destination)
                except (ValueError, RuntimeError, StopIteration):
                    destination.unlink()
            if not destination.exists():
                source = Path(clip["local_path"]) if "local_path" in clip else output / (name + ".source.mp4")
                if not source.exists():
                    download(clip["url"], source)
                layout = render(source, trip["reel"]["overlay_text"], destination, args.font)
                if "local_path" not in clip:
                    source.unlink(missing_ok=True)
                print(f"Rendered reel {position}: {destination.stat().st_size / 1024 / 1024:.1f} MB, font {layout['font_size']} px")
            identifier = render_id(trip["id"], position, clip["id"], trip["reel"]["overlay_text"],
                                   batch.get("generation_id", ""))
            thumbnail = destination.with_suffix(".jpg")
            if not thumbnail.exists():
                command(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(destination),
                         "-frames:v", "1", str(thumbnail)])
            entry = {"city": clip["city"], "pexels_video_id": clip["id"],
                     "pexels_page_url": clip["page_url"], "pexels_attribution": clip["attribution"],
                     "render_id": identifier, "render_status": "succeeded"}
            if storage:
                key = f"reels/v1/trip-{trip['id']}/{identifier}"
                entry["render_url"] = storage.upload(destination, key + ".mp4")
                entry["snapshot_url"] = storage.upload(destination.with_suffix(".jpg"), key + ".jpg")
            else:
                entry["local_file"] = destination.name
            batch["renders"][str(position)] = entry
            write_json(batch_path, batch)
        except Exception as error:
            # Preserve completed files and metadata; never queue a partial batch.
            failures.append(position)
            print(f"Reel {position} failed: {failure_detail(error)}; rerun this output directory to retry")
    if failures:
        raise RuntimeError(f"Incomplete batch; failed positions: {failures}")

    (output / "caption.txt").write_text(trip["reel"]["caption"] + "\n")
    if args.publish:
        payload = build_payload(trip, [batch["renders"][str(i)] for i in range(1, 7)])
        write_json(output / "queue-payload.json", payload)
        response = api.save(payload)
        confirmed = validate_queue_response(payload, response)
        batch["queued"] = True
        batch["queue_batch_key"] = confirmed["batch_key"]
        batch["queue_created"] = confirmed["created"]
        write_json(batch_path, batch)
        if confirmed["created"]:
            print("Six new drafts saved for manual review. No Instagram posting action was performed.")
        else:
            print("Six existing active drafts confirmed; no new drafts created.")
    elapsed = time.monotonic() - started
    total_mb = sum(p.stat().st_size for p in output.glob("reel-??.mp4")) / 1024 / 1024
    summary = {"trip_id": trip["id"], "reels": 6, "seconds": round(elapsed, 1),
               "video_mb": round(total_mb, 1), "queued": batch["queued"],
               "new_drafts": 6 if batch.get("queue_created") else 0,
               "completed_at": datetime.now(timezone.utc).isoformat()}
    write_json(output / "summary.json", summary)
    print(json.dumps(summary))


def main():
    parser = argparse.ArgumentParser(description="Render six LeavePrints reels without Creatomate")
    parser.add_argument("--output", default="reel-output")
    parser.add_argument("--trip-file", help="API-shaped trip JSON; avoids a trip API request")
    parser.add_argument("--clips-dir", help="Six local MP4s for offline testing")
    parser.add_argument("--font", default=os.environ.get("REEL_FONT_PATH", DEFAULT_FONT))
    parser.add_argument("--publish", action="store_true", help="Upload videos and save drafts; never post to Instagram")
    args = parser.parse_args()
    if args.publish and args.clips_dir:
        parser.error("Local test footage cannot be published to the production queue")
    try:
        run(args)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"Generation stopped: {error}\n")


if __name__ == "__main__":
    main()
