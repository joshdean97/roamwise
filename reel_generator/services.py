import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing configuration: {name}")
    return value


def request_json(url, headers=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": "LeavePrints-Reels/1", **(headers or {})}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=45) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(f"API returned HTTP {error.code}") from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError("API request failed after three attempts") from None
        time.sleep(2 ** (attempt + 1))


class ContentAPI:
    def __init__(self):
        self.base = required("LEAVEPRINTS_URL").rstrip("/")
        if urlparse(self.base).scheme != "https":
            raise ValueError("LEAVEPRINTS_URL must use HTTPS")
        self.headers = {"Authorization": "Bearer " + required("CONTENT_API_KEY")}

    def trips(self):
        return request_json(self.base + "/api/admin/content/trips?" + urlencode({
            "limit": 20, "unused": "true", "platform": "instagram", "format": "trial_reel"
        }), self.headers)["trips"]

    def save(self, payload):
        # Stable render IDs make a retry safe if the first response was lost.
        return request_json(self.base + "/api/admin/content/reel-drafts", self.headers, payload)


def select_clips(videos, exclude=()):
    clips = []
    for video in videos:
        if str(video["id"]) in exclude or float(video.get("duration", 0)) < 6:
            continue
        files = [f for f in video.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
                 and f["height"] > f["width"] and f["width"] >= 720]
        if not files:
            continue
        chosen = min(files, key=lambda f: abs(f["width"] - 1080))
        clips.append({"id": str(video["id"]), "url": chosen["link"],
                      "page_url": video["url"],
                      "attribution": f"Video by {video['user']['name']} on Pexels"[:255]})
        if len(clips) == 2:
            break
    if len(clips) != 2:
        raise ValueError("Not enough suitable distinct portrait clips for this city")
    return clips


def search_clips(destination, exclude=()):
    data = request_json("https://api.pexels.com/videos/search?" + urlencode({
        "query": f"{destination['city']} {destination['country']}",
        "orientation": "portrait", "size": "medium", "per_page": 30
    }), {"Authorization": required("PEXELS_API_KEY")})
    return select_clips(data.get("videos", []), exclude)


def download(url, path):
    path = Path(path)
    if urlparse(url).scheme != "https":
        raise ValueError("Clip URLs must use HTTPS")
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "LeavePrints-Reels/1"}), timeout=60) as response:
                size = 0
                with path.with_suffix(".part").open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > 150 * 1024 * 1024:
                            raise ValueError("Source exceeds the 150 MB download limit")
                        stream.write(chunk)
            path.with_suffix(".part").replace(path)
            return
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError("Clip download failed after three attempts") from None
            time.sleep(2 ** (attempt + 1))


class ObjectStorage:
    """S3-compatible storage; no bucket provisioning or paid resources created."""
    def __init__(self):
        import boto3
        self.bucket = required("REEL_STORAGE_BUCKET")
        self.public_url = required("REEL_STORAGE_PUBLIC_URL").rstrip("/")
        if urlparse(self.public_url).scheme != "https":
            raise ValueError("REEL_STORAGE_PUBLIC_URL must use HTTPS")
        self.client = boto3.client(
            "s3", endpoint_url=required("REEL_STORAGE_ENDPOINT"),
            aws_access_key_id=required("REEL_STORAGE_ACCESS_KEY_ID"),
            aws_secret_access_key=required("REEL_STORAGE_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("REEL_STORAGE_REGION") or "auto")

    def upload(self, path, key):
        path = Path(path)
        content_type = "video/mp4" if path.suffix == ".mp4" else "image/jpeg"
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs={
            "ContentType": content_type, "CacheControl": "public, max-age=86400"})
        url = self.public_url + "/" + quote(key, safe="/")
        # Ensure the queue receives usable public URLs, not private bucket URLs.
        with urlopen(Request(url, method="HEAD"), timeout=30) as response:
            if response.status != 200:
                raise RuntimeError("Uploaded media is not publicly accessible")
        return url
