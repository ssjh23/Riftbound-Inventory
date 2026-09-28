"""Shared ingest steps: validate, re-encode, hash, and store card images.

Security posture for external images (OWASP File Upload Cheat Sheet):
  * HTTPS only, and only from an explicit host allowlist.
  * Content-Type and size are checked before the body is fully read.
  * Every image is decoded and re-encoded with Pillow before it is stored.
    Re-encoding produces a brand-new JPEG containing only pixel data, which
    strips EXIF/metadata and any payload smuggled into the original file.
    SVG is never accepted (SVG can carry scripts).
  * File names are derived from the validated card id, never from the URL.
"""

import io
import re

import httpx
import imagehash
from PIL import Image

from ..config import data_dir

CARD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

ALLOWED_IMAGE_HOSTS = {
    "images.scrydex.com",
    "cdn.scrydex.com",
    "playriftbound.com",
    "cdn.rgpub.io",  # Riot's public asset CDN
    "cmsassets.rgpub.io",  # Riot's Sanity CMS — hosts official card images
    "assetcdn.rgpub.io",
}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Identify ourselves honestly when scraping; a descriptive UA is basic
# scraping etiquette and lets the site operator contact/block us if needed.
USER_AGENT = "riftbound-inventory/0.1 (personal collection tool)"


class IngestError(Exception):
    pass


def validate_card_id(card_id: str) -> str:
    if not CARD_ID_RE.match(card_id):
        raise IngestError(f"unsafe card id: {card_id!r}")
    return card_id


def reencode(img: Image.Image) -> bytes:
    """Return a clean JPEG (pixels only, no metadata) of the image."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def store_card_image(card_id: str, img: Image.Image) -> tuple[str, str]:
    """Persist a normalized image; return (image_file, phash_hex)."""
    validate_card_id(card_id)
    phash = str(imagehash.phash(img))
    filename = f"{card_id}.jpg"
    (data_dir() / "images" / filename).write_bytes(reencode(img))
    return filename, phash


def download_image(url: str, client: httpx.Client | None = None) -> Image.Image:
    """Fetch an external card image with the checks described above."""
    parsed = httpx.URL(url)
    if parsed.scheme != "https":
        raise IngestError(f"refusing non-HTTPS image URL: {url}")
    if parsed.host not in ALLOWED_IMAGE_HOSTS:
        raise IngestError(f"image host not in allowlist: {parsed.host}")

    own_client = client is None
    client = client or httpx.Client(
        timeout=30, follow_redirects=False, headers={"User-Agent": USER_AGENT}
    )
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip()
            if ctype not in ALLOWED_CONTENT_TYPES:
                raise IngestError(f"unexpected content type {ctype!r} for {url}")
            declared = resp.headers.get("content-length")
            if declared and int(declared) > MAX_IMAGE_BYTES:
                raise IngestError(f"image too large: {url}")
            body = io.BytesIO()
            for chunk in resp.iter_bytes():
                body.write(chunk)
                if body.tell() > MAX_IMAGE_BYTES:
                    raise IngestError(f"image exceeded size cap mid-stream: {url}")
    finally:
        if own_client:
            client.close()

    body.seek(0)
    try:
        img = Image.open(body)
        img.load()
    except Exception as exc:
        raise IngestError(f"file from {url} is not a decodable image") from exc
    return img
