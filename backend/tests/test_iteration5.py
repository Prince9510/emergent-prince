"""Iteration 5 tests: Related content, Image optimization (WebP), Media delete."""
import io
import os
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://react-cms-pro.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@studiovoxel.co")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "VoxelAdmin2026!")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def admin_session(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return session


# ---------------- Related endpoint ----------------
class TestRelated:
    def test_related_ok(self, session):
        # NOTE: project spec said 'react-cms-pro' but that's the app name; use a real seeded slug.
        slug = "shoreline-cabin"
        r = session.get(f"{BASE_URL}/api/projects/{slug}/related")
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(["posts", "testimonial", "projects"]).issubset(data.keys())
        assert isinstance(data["posts"], list) and len(data["posts"]) <= 3
        assert isinstance(data["projects"], list) and len(data["projects"]) <= 3
        # exclude current slug
        for p in data["projects"]:
            assert p.get("slug") != slug
        # posts must be active+published
        for post in data["posts"]:
            assert post.get("active") is True
            assert post.get("published") is True

    def test_related_invalid_slug(self, session):
        r = session.get(f"{BASE_URL}/api/projects/does-not-exist-xyz/related")
        assert r.status_code == 404


# ---------------- Media upload optimization ----------------
def _make_jpg_bytes(w=2400, h=1800, color=(120, 200, 90)):
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_png_bytes(w=800, h=600):
    img = Image.new("RGBA", (w, h), (10, 20, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestMediaUpload:
    uploaded_ids = []

    def test_upload_jpg_converts_to_webp_and_resizes(self, admin_session):
        jpg = _make_jpg_bytes(2400, 1800)
        files = {"files": ("TEST_big.jpg", jpg, "image/jpeg")}
        r = admin_session.post(f"{BASE_URL}/api/media/upload", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        items = body.get("items")
        assert isinstance(items, list) and len(items) == 1
        item = items[0]
        assert item["content_type"] == "image/webp"
        assert item["url"].endswith(".webp")
        assert item["original_name"].endswith(".webp")
        assert "width" in item and "height" in item
        # resized to max 1920
        assert max(item["width"], item["height"]) <= 1920
        assert max(item["width"], item["height"]) == 1920
        TestMediaUpload.uploaded_ids.append(item["id"])

        # Serve via /api/uploads/... through public ingress and verify WebP magic bytes.
        assert item["url"].startswith("/api/uploads/"), f"URL must start with /api/uploads/: {item['url']}"
        served = requests.get(f"{BASE_URL}{item['url']}")
        assert served.status_code == 200
        assert "image/webp" in served.headers.get("content-type", ""), f"content-type: {served.headers.get('content-type')}"
        data = served.content
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", "Served file is not a valid WebP"

    def test_upload_rejects_non_image_content_type(self, admin_session):
        files = {"files": ("TEST_note.txt", b"hello world", "text/plain")}
        r = admin_session.post(f"{BASE_URL}/api/media/upload", files=files)
        assert r.status_code == 400

    def test_upload_rejects_malformed_image(self, admin_session):
        # Content-type says image/jpeg but body is garbage
        files = {"files": ("TEST_fake.jpg", b"not really an image at all", "image/jpeg")}
        r = admin_session.post(f"{BASE_URL}/api/media/upload", files=files)
        assert r.status_code == 400
        assert "not a valid image" in r.text.lower() or "valid image" in r.text.lower()

    def test_upload_rejects_over_8mb(self, admin_session):
        # Create ~9MB JPEG
        big = _make_jpg_bytes(6000, 4500, color=(255, 128, 64))
        # If still under 8MB, pad with additional file bytes doesn't help since server reads real content.
        # Ensure we exceed 8MB
        if len(big) <= 8 * 1024 * 1024:
            # Fall back: create huge PNG which compresses less
            img = Image.new("RGB", (5000, 5000))
            # noisy pixels don't compress well
            import random
            px = img.load()
            for _ in range(200000):
                x = random.randint(0, 4999); y = random.randint(0, 4999)
                px[x, y] = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=100, subsampling=0)
            big = buf.getvalue()
        assert len(big) > 8 * 1024 * 1024, f"Test payload only {len(big)} bytes"
        files = {"files": ("TEST_huge.jpg", big, "image/jpeg")}
        r = admin_session.post(f"{BASE_URL}/api/media/upload", files=files)
        assert r.status_code == 400

    def test_delete_media_removes_record_and_file(self, admin_session):
        # upload a small PNG we can delete
        png = _make_png_bytes()
        files = {"files": ("TEST_small.png", png, "image/png")}
        r = admin_session.post(f"{BASE_URL}/api/media/upload", files=files)
        assert r.status_code == 200
        item = r.json()["items"][0]
        item_id = item["id"]
        url = item["url"]

        # confirm served via internal backend (external /uploads goes to SPA)
        served = requests.get(f"http://localhost:8001{url}")
        assert served.status_code == 200

        # delete
        d = admin_session.delete(f"{BASE_URL}/api/media/{item_id}")
        assert d.status_code == 200, d.text
        assert d.json().get("success") is True

        # confirm 404 on subsequent delete
        d2 = admin_session.delete(f"{BASE_URL}/api/media/{item_id}")
        assert d2.status_code == 404

        # confirm physical file gone (via backend)
        served2 = requests.get(f"http://localhost:8001{url}")
        assert served2.status_code == 404

    def test_media_upload_requires_auth(self):
        jpg = _make_jpg_bytes(100, 100)
        r = requests.post(f"{BASE_URL}/api/media/upload", files={"files": ("TEST_x.jpg", jpg, "image/jpeg")})
        assert r.status_code in (401, 403)


# ---------------- Cleanup ----------------
def test_zzz_cleanup(admin_session):
    for item_id in list(TestMediaUpload.uploaded_ids):
        admin_session.delete(f"{BASE_URL}/api/media/{item_id}")
