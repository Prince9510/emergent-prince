"""Iteration 7 tests: bulk media actions + contact analytics."""
import io
import os
import time
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@studiovoxel.co"
ADMIN_PASSWORD = "VoxelAdmin2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


def _upload_image(session, name="TEST_bulk.jpg"):
    img = Image.new("RGB", (400, 300), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    r = session.post(f"{BASE_URL}/api/media/upload", files={"files": (name, buf.getvalue(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()["items"][0]


# ---------------- Bulk delete ----------------
class TestBulkDelete:
    def test_unauth_401(self):
        r = requests.post(f"{BASE_URL}/api/media/bulk-delete", json={"ids": ["x"]})
        assert r.status_code in (401, 403)

    def test_empty_ids_returns_zero(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/media/bulk-delete", json={"ids": []})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["deleted"] == 0

    def test_deletes_db_and_files(self, admin_session):
        a = _upload_image(admin_session, "TEST_bulkdel_a.jpg")
        b = _upload_image(admin_session, "TEST_bulkdel_b.jpg")
        # confirm files exist on disk
        for item in (a, b):
            p = f"/app/backend/uploads/{item['filename']}"
            assert os.path.exists(p), f"missing {p}"
        r = admin_session.post(f"{BASE_URL}/api/media/bulk-delete", json={"ids": [a["id"], b["id"]]})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["deleted"] == 2
        # verify DB rows gone
        listing = admin_session.get(f"{BASE_URL}/api/media").json()
        ids = {m["id"] for m in listing}
        assert a["id"] not in ids and b["id"] not in ids
        # verify files gone
        for item in (a, b):
            assert not os.path.exists(f"/app/backend/uploads/{item['filename']}")


# ---------------- Bulk tag ----------------
class TestBulkTag:
    def test_unauth_401(self):
        r = requests.post(f"{BASE_URL}/api/media/bulk-tag", json={"ids": ["x"], "tags": ["y"]})
        assert r.status_code in (401, 403)

    def test_empty_tags_updated_zero(self, admin_session):
        item = _upload_image(admin_session, "TEST_bulktag_empty.jpg")
        try:
            r = admin_session.post(f"{BASE_URL}/api/media/bulk-tag", json={"ids": [item["id"]], "tags": []})
            assert r.status_code == 200
            assert r.json()["updated"] == 0
        finally:
            admin_session.post(f"{BASE_URL}/api/media/bulk-delete", json={"ids": [item["id"]]})

    def test_addToSet_dedups_tags(self, admin_session):
        item = _upload_image(admin_session, "TEST_bulktag.jpg")
        try:
            # First apply
            r = admin_session.post(f"{BASE_URL}/api/media/bulk-tag", json={"ids": [item["id"]], "tags": ["brand", "2026"]})
            assert r.status_code == 200 and r.json()["success"] is True
            # Second time same tags - should not duplicate
            r2 = admin_session.post(f"{BASE_URL}/api/media/bulk-tag", json={"ids": [item["id"]], "tags": ["brand"]})
            assert r2.status_code == 200
            # verify listing has tags array
            listing = admin_session.get(f"{BASE_URL}/api/media").json()
            match = next((m for m in listing if m["id"] == item["id"]), None)
            assert match is not None, "media item not returned in listing"
            assert "tags" in match, f"tags key missing in {match}"
            tags = match["tags"]
            assert isinstance(tags, list)
            assert sorted(tags) == sorted(list(set(tags))), "duplicates present"
            assert "brand" in tags and "2026" in tags
        finally:
            admin_session.post(f"{BASE_URL}/api/media/bulk-delete", json={"ids": [item["id"]]})


# ---------------- Analytics ----------------
class TestAnalytics:
    def test_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/analytics/contacts")
        assert r.status_code in (401, 403)

    def test_shape_and_live_increment(self, admin_session):
        # baseline
        r0 = admin_session.get(f"{BASE_URL}/api/analytics/contacts")
        assert r0.status_code == 200, r0.text
        base = r0.json()
        assert "weeks" in base and "top_types" in base and "total" in base
        assert isinstance(base["weeks"], list) and len(base["weeks"]) == 6
        for w in base["weeks"]:
            assert "label" in w and "total" in w
        assert isinstance(base["top_types"], list) and len(base["top_types"]) <= 5
        base_current_week = base["weeks"][-1]["total"]
        base_total = base["total"]

        # post a fresh contact
        marker = f"TEST_it7_analytics_{int(time.time())}"
        payload = {
            "name": marker,
            "email": "it7probe@example.com",
            "message": "iteration 7 analytics probe",
            "project_type": marker,
        }
        cr = requests.post(f"{BASE_URL}/api/contact", json=payload)
        assert cr.status_code in (200, 201), cr.text

        # re-fetch
        r1 = admin_session.get(f"{BASE_URL}/api/analytics/contacts")
        assert r1.status_code == 200
        after = r1.json()
        assert after["total"] == base_total + 1
        assert after["weeks"][-1]["total"] == base_current_week + 1
        types_found = {t["project_type"] for t in after["top_types"]}
        # top_types may cap at 5; if marker unique it should appear (count=1). If already >5 buckets with higher counts, allow miss.
        if len(after["top_types"]) < 5:
            assert marker in types_found, f"marker {marker} not in top_types {after['top_types']}"

        # cleanup: delete the submission we made
        subs = admin_session.get(f"{BASE_URL}/api/contact-submissions").json()
        for sub in subs:
            if sub.get("name") == marker:
                admin_session.delete(f"{BASE_URL}/api/contact-submissions/{sub['id']}")
