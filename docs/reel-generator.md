# LeavePrints reel generator

Replaces Creatomate and Make's rendering orchestration with Python, Pillow and
FFmpeg. It uses the existing content API and `/admin/reels` review queue. The
Flask application and its dependencies are unchanged. No Instagram API calls,
`/used` calls, subscription cancellations or cloud provisioning are performed.

## What is implemented

- Three cities, two distinct Pexels portrait clips per city, six separate reels.
- Six-second, silent H.264/yuv420p MP4s, 1080 × 1920 at 30 fps, fast-start playback.
- Centre-cropped footage and automatically wrapped white serif text with black
  outline and blurred shadow, inside a safe area for Instagram controls.
- Caption/costs from the API; the first overlay line becomes “I made a website
  to budget trips…”. Currency symbols and arrows are supported. Flags become
  country-code labels and transport emoji become words with the portable font.
- Thumbnails, source attribution, local manifests, measured render time/file size.
- S3-compatible uploads, public URL checks, exactly-six queue submissions and
  deterministic render IDs for idempotent API retries.
- A daily GitHub workflow at 03:17 UTC, manual runs, concurrency protection,
  and two-day artifacts that restore an interrupted attempt for the same date.

The existing queue supports approve/reject, copy caption, download and mark
posted. Caption editing and per-reel regeneration buttons are not added in this
first implementation. Destination accuracy still requires human review because
Pexels keyword search can return unrelated footage. No generic destination
fallback is substituted silently.

## Local use

Install Python 3.12+, FFmpeg/ffprobe and the DejaVu fonts. Then:

```bash
python -m pip install -r requirements-reels.txt
export LEAVEPRINTS_URL=https://www.leaveprints.com
# Set CONTENT_API_KEY and PEXELS_API_KEY securely in your shell/session.
python -m reel_generator --output reel-output
```

Without `--publish`, MP4s and captions are saved locally and the review queue is
untouched. To test entirely offline, provide an API-shaped trip object and
exactly six local MP4s, each at least six seconds long:

```bash
python -m reel_generator --trip-file trip.json --clips-dir ./clips --output reel-output
```

Rerun the same output directory to resume. It pins the trip and chosen clips;
valid completed videos are reused. Corrupt output is rendered again. A new
output directory starts a new batch. A completed queued batch is a no-op.
Never reuse a directory for a different trip or change fonts midway through
a retry. Clearing or replacing a clip requires a new batch directory; this
initial release does not implement the planned regeneration UI.

## Cloud storage prerequisite

The current application stores media URLs, not video bytes. It has no reusable
object-storage integration in the inspected source. Configure an existing
S3-compatible bucket or choose a provider and verify its current free allowance
before activating automation. This code does not assume storage is free.

Cloudflare R2 Standard is a suitable candidate: its published free allowance is
10 GB-month of storage, 1 million Class A operations and 10 million Class B
operations, with free direct egress. Verify the account's total usage and billing
before enabling it: https://developers.cloudflare.com/r2/pricing/ . The offline
six-reel test batch produced approximately 17.2 MB of video in 57 seconds on the
development machine. That is a benchmark, not a GitHub runtime or real-footage
storage guarantee.

Use a dedicated `reels/` prefix. Serve objects through a public HTTPS origin
that supports MP4 byte-range playback. Restrict its upload key to the selected
bucket/prefix. Configure retention deliberately: deleting an object breaks the
queue preview. For example, a 30-day lifecycle on **this prefix only** can bound
usage if older drafts no longer need playback. No deletion job is included.
Bucket CORS may be needed for cross-origin media access; test on the actual
LeavePrints origin and phone browser before switching over.

## GitHub configuration

Repository Actions variables:

| Variable | Value |
| --- | --- |
| `REELS_ENABLED` | Leave unset until ready; `true` enables scheduled/manual jobs |
| `LEAVEPRINTS_URL` | `https://www.leaveprints.com` |
| `REEL_STORAGE_PUBLIC_URL` | Public HTTPS media origin, without trailing slash |
| `REEL_STORAGE_REGION` | Provider region; defaults to `auto` |

Repository Actions secrets:

- `CONTENT_API_KEY`: existing LeavePrints content API key.
- `PEXELS_API_KEY`: existing Pexels API key.
- `REEL_STORAGE_ENDPOINT`: S3-compatible HTTPS endpoint.
- `REEL_STORAGE_BUCKET`: bucket name.
- `REEL_STORAGE_ACCESS_KEY_ID` and `REEL_STORAGE_SECRET_ACCESS_KEY`.

Do not paste keys into source files, logs, commits or issues. All listed values
are checked before the production run proceeds. The GitHub connection used
to author this change cannot manage repository Actions secrets; they must be
configured through an authorized account/API outside that connector.

## Retry and usage behaviour

Reels that finish before another fails remain in the batch artifact. The queue
receives nothing until all six are rendered and uploaded. Rerun the workflow
with the same UTC `batch_date` within two days to recover its artifact. After
artifact expiry, retry state is unavailable; download/back up a failed batch
if it will need longer to resolve. Do not assume an older date restores data.
GitHub concurrency protects this workflow only: disable overlapping Make
generation before activating the daily schedule. Existing API duplicate checks
protect repeated submissions of identical render IDs, but do not reserve a trip
against a separate concurrent producer.

Successful outputs remain in cloud storage; GitHub artifacts are temporary
downloads/retry checkpoints, not the queue's playback source. Downloads of
input footage and overlay PNGs are excluded from artifacts. The workflow uses
read-only repository and Actions permissions. Schedules are best-effort and
should precede the intended review time by several hours.

Measure total billed job minutes (including dependency installation) and cloud
storage after a real batch. Avoid promising zero cost solely from render time.
Set a spending limit appropriate to your account and check existing workflows'
shared allowance. This implementation cannot configure GitHub billing.

## Validation and switch-over

1. Render an offline sample and inspect text/crop/playback on a phone.
2. Configure secrets and storage, then manually generate one live batch.
3. Confirm all six thumbnails and videos load inside `/admin/reels`; download
   one on Android and verify caption, attribution, approve/reject/mark-posted.
4. Check interrupted-run retries, API idempotency and measured job/storage usage.
5. Disable Make generation, enable `REELS_ENABLED`, and observe three daily batches.
6. Cancel Creatomate only after the replacement is proven and old needed media
   has been downloaded. The code does not cancel subscriptions automatically.

Generator tests: `python -m pytest tests/test_reel_generator.py`. Existing API
tests: `python -m pytest tests/test_content_api.py` after installing the app and
development requirements. A real FFmpeg encode/decode sample is required in
addition to the unit tests before cutover.
