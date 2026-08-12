"""Tests for iteration 4: blog draft filtering, contact submissions CRUD, dashboard unread count."""
import os, requests, pytest

BASE = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
CREDS = {'email': 'admin@studiovoxel.co', 'password': 'VoxelAdmin2026!'}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(BASE + '/api/auth/login', json=CREDS, timeout=20)
    assert r.status_code == 200, r.text
    s.headers['Authorization'] = 'Bearer ' + r.json()['access_token']
    return s


# Blog draft filtering
def test_public_blog_hides_drafts_admin_can_include(admin_session):
    payload = {'title': 'TEST Draft Post iter4', 'excerpt': 'A hidden draft excerpt line.',
               'content': 'This is sufficiently long draft content body text.',
               'author': 'Tester', 'cover_image_url': '', 'tags': 'test,draft',
               'published': False, 'order': 999}
    r = admin_session.post(BASE + '/api/blog', json=payload)
    assert r.status_code == 200, r.text
    post = r.json(); pid = post['id']; slug = post['slug']
    try:
        # public list excludes it
        pub = requests.get(BASE + '/api/blog', timeout=20).json()
        assert all(p['id'] != pid for p in pub), "Draft should be hidden from public"
        # admin with include_drafts sees it
        adm = admin_session.get(BASE + '/api/blog?include_drafts=true').json()
        assert any(p['id'] == pid for p in adm), "Admin include_drafts should show draft"
        # public /api/blog?include_drafts=true (no auth) still excludes it
        pub2 = requests.get(BASE + '/api/blog?include_drafts=true', timeout=20).json()
        assert all(p['id'] != pid for p in pub2), "include_drafts must require auth"
    finally:
        admin_session.delete(BASE + f'/api/blog/{pid}')


# Contact submissions endpoints
def test_contact_submissions_auth_and_crud(admin_session):
    # unauth
    assert requests.get(BASE + '/api/contact-submissions').status_code == 401
    # seed a fresh one
    cr = requests.post(BASE + '/api/contact', json={
        'name': 'TEST Iter4 Contact', 'email': 'iter4@example.com',
        'project_type': 'Kitchen',
        'message': 'This is a sufficiently long enquiry message for testing.'})
    assert cr.status_code == 200
    lst = admin_session.get(BASE + '/api/contact-submissions').json()
    assert isinstance(lst, list) and len(lst) > 0
    target = next((x for x in lst if x['email'] == 'iter4@example.com'), None)
    assert target is not None
    sid = target['id']
    assert target['status'] == 'new'

    # invalid status -> 422
    inv = admin_session.put(BASE + f'/api/contact-submissions/{sid}', json={'status': 'foo'})
    assert inv.status_code == 422

    # unauth PUT
    assert requests.put(BASE + f'/api/contact-submissions/{sid}', json={'status': 'read'}).status_code == 401

    # mark read
    upd = admin_session.put(BASE + f'/api/contact-submissions/{sid}', json={'status': 'read'})
    assert upd.status_code == 200
    assert upd.json()['status'] == 'read'

    # archived
    upd2 = admin_session.put(BASE + f'/api/contact-submissions/{sid}', json={'status': 'archived'})
    assert upd2.status_code == 200 and upd2.json()['status'] == 'archived'

    # unauth delete
    assert requests.delete(BASE + f'/api/contact-submissions/{sid}').status_code == 401
    # delete missing
    assert admin_session.delete(BASE + '/api/contact-submissions/nonexistent-id-xyz').status_code == 404
    # delete existing
    assert admin_session.delete(BASE + f'/api/contact-submissions/{sid}').status_code == 200


def test_dashboard_includes_unread_contacts_and_increments(admin_session):
    d1 = admin_session.get(BASE + '/api/dashboard').json()
    assert 'contact_submissions' in d1['stats'] and 'unread_contacts' in d1['stats']
    before = d1['stats']['unread_contacts']
    cr = requests.post(BASE + '/api/contact', json={
        'name': 'TEST Iter4 Unread', 'email': 'iter4-unread@example.com',
        'project_type': 'Kitchen',
        'message': 'Sufficiently long enquiry message for unread counter test.'})
    assert cr.status_code == 200
    d2 = admin_session.get(BASE + '/api/dashboard').json()
    assert d2['stats']['unread_contacts'] == before + 1
    # cleanup
    lst = admin_session.get(BASE + '/api/contact-submissions').json()
    for item in lst:
        if item['email'] == 'iter4-unread@example.com':
            admin_session.delete(BASE + f"/api/contact-submissions/{item['id']}")
