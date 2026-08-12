import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://react-cms-pro.preview.emergentagent.com").rstrip("/")
CREDS = {"email": "admin@studiovoxel.co", "password": "VoxelAdmin2026!"}


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=CREDS, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    s.headers["Authorization"] = f"Bearer {token}"
    return s


# ---------- Public GETs ----------
def test_get_testimonials_seeded():
    r = requests.get(f"{BASE}/api/testimonials", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 3
    assert "_id" not in r.text
    assert all("quote" in t and "title" in t for t in data)


def test_get_team_seeded():
    r = requests.get(f"{BASE}/api/team", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 4
    assert all("role" in t and "title" in t for t in data)


def test_get_faqs_seeded():
    r = requests.get(f"{BASE}/api/faqs", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 6
    assert all("answer" in f and "title" in f for f in data)


def test_get_blog_and_by_slug():
    r = requests.get(f"{BASE}/api/blog", timeout=20)
    assert r.status_code == 200
    posts = r.json()
    assert isinstance(posts, list) and len(posts) >= 3
    slugs = [p["slug"] for p in posts]
    assert "making-room-for-the-good-stuff" in slugs
    r2 = requests.get(f"{BASE}/api/blog/making-room-for-the-good-stuff", timeout=20)
    assert r2.status_code == 200
    p = r2.json()
    assert p["title"] == "Making room for the good stuff"
    assert "content" in p and len(p["content"]) > 20


def test_blog_slug_404():
    r = requests.get(f"{BASE}/api/blog/does-not-exist-xyz", timeout=20)
    assert r.status_code == 404


def test_site_home_has_testimonials_and_team():
    r = requests.get(f"{BASE}/api/site/home", timeout=20)
    assert r.status_code == 200
    d = r.json()
    for key in ["services", "projects", "gallery", "testimonials", "team"]:
        assert key in d, key
    assert len(d["testimonials"]) >= 1
    assert len(d["team"]) >= 1


# ---------- Auth required ----------
@pytest.mark.parametrize("method,path", [
    ("post", "/api/testimonials"),
    ("put", "/api/testimonials/x"),
    ("delete", "/api/testimonials/x"),
    ("post", "/api/team"),
    ("put", "/api/team/x"),
    ("delete", "/api/team/x"),
    ("post", "/api/faqs"),
    ("put", "/api/faqs/x"),
    ("delete", "/api/faqs/x"),
    ("post", "/api/blog"),
    ("put", "/api/blog/x"),
    ("delete", "/api/blog/x"),
])
def test_unauthenticated_writes_return_401(method, path):
    r = requests.request(method, f"{BASE}{path}", json={}, timeout=20)
    assert r.status_code == 401, (method, path, r.status_code, r.text)


# ---------- Dashboard stats include new collections ----------
def test_dashboard_stats(auth_session):
    r = auth_session.get(f"{BASE}/api/dashboard", timeout=20)
    assert r.status_code == 200
    stats = r.json()["stats"]
    for k in ["testimonials", "blog", "team", "faqs", "services", "projects", "gallery", "media"]:
        assert k in stats, k
    assert stats["testimonials"] >= 3
    assert stats["team"] >= 4
    assert stats["faqs"] >= 6
    assert stats["blog"] >= 3


# ---------- CRUD Testimonials ----------
def test_testimonial_crud(auth_session):
    payload = {"title": "TEST Reviewer", "role": "CTO", "company": "TestCo",
               "quote": "This is a wonderfully sufficient quote for testing.",
               "image_url": "", "rating": 5, "featured": True, "order": 50, "active": True}
    r = auth_session.post(f"{BASE}/api/testimonials", json=payload); assert r.status_code == 200
    item = r.json(); assert item["title"] == payload["title"]; rid = item["id"]
    r = auth_session.put(f"{BASE}/api/testimonials/{rid}", json={**payload, "title": "TEST Reviewer Updated"})
    assert r.status_code == 200 and r.json()["title"] == "TEST Reviewer Updated"
    # verify persistence via list
    lst = requests.get(f"{BASE}/api/testimonials").json()
    assert any(t["id"] == rid and t["title"] == "TEST Reviewer Updated" for t in lst)
    assert auth_session.delete(f"{BASE}/api/testimonials/{rid}").status_code == 200
    lst = requests.get(f"{BASE}/api/testimonials").json()
    assert not any(t["id"] == rid for t in lst)


# ---------- CRUD Team ----------
def test_team_crud(auth_session):
    payload = {"title": "TEST Member", "role": "Tester", "bio": "Bio here",
               "image_url": "", "instagram": "", "linkedin": "", "order": 99, "active": True}
    r = auth_session.post(f"{BASE}/api/team", json=payload); assert r.status_code == 200
    rid = r.json()["id"]
    r = auth_session.put(f"{BASE}/api/team/{rid}", json={**payload, "role": "Senior Tester"})
    assert r.status_code == 200 and r.json()["role"] == "Senior Tester"
    assert auth_session.delete(f"{BASE}/api/team/{rid}").status_code == 200


# ---------- CRUD FAQs ----------
def test_faq_crud(auth_session):
    payload = {"title": "TEST question about testing?", "answer": "TEST answer body.",
               "category": "General", "order": 88, "active": True}
    r = auth_session.post(f"{BASE}/api/faqs", json=payload); assert r.status_code == 200
    rid = r.json()["id"]
    r = auth_session.put(f"{BASE}/api/faqs/{rid}", json={**payload, "answer": "Updated answer body."})
    assert r.status_code == 200 and r.json()["answer"] == "Updated answer body."
    assert auth_session.delete(f"{BASE}/api/faqs/{rid}").status_code == 200


# ---------- CRUD Blog + slug generation ----------
def test_blog_crud_slug_generation(auth_session):
    payload = {"title": "TEST My New Post Title!!", "excerpt": "A short test excerpt for coverage.",
               "content": "This is content that is definitely long enough to pass validation.",
               "image_url": "", "author": "QA", "tags": "test", "published": True, "order": 77, "active": True}
    r = auth_session.post(f"{BASE}/api/blog", json=payload); assert r.status_code == 200
    item = r.json(); assert item["slug"] == "test-my-new-post-title"; rid = item["id"]
    # get by slug
    r2 = requests.get(f"{BASE}/api/blog/{item['slug']}"); assert r2.status_code == 200
    # update updates slug
    r = auth_session.put(f"{BASE}/api/blog/{rid}", json={**payload, "title": "TEST Renamed Post"})
    assert r.status_code == 200 and r.json()["slug"] == "test-renamed-post"
    assert auth_session.delete(f"{BASE}/api/blog/{rid}").status_code == 200
