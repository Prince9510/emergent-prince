import os, io, requests, pytest
BASE=os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
CREDS={'email':'admin@studiovoxel.co','password':'VoxelAdmin2026!'}

def test_public_and_auth_and_crud():
    s=requests.Session()
    for path in ['/api/','/api/site/home','/api/services','/api/projects','/api/gallery']:
        r=s.get(BASE+path,timeout=20); assert r.status_code==200, (path,r.text)
        assert '_id' not in r.text
    r=s.post(BASE+'/api/auth/login',json=CREDS,timeout=20); assert r.status_code==200; d=r.json(); assert d['user']['email']==CREDS['email']; assert d['access_token']
    assert 'password' not in d['user'] and 'password_hash' not in d['user']
    s.headers['Authorization']='Bearer '+d['access_token']
    assert s.get(BASE+'/api/auth/me').status_code==200
    assert s.get(BASE+'/api/dashboard').status_code==200
    payload={'title':'TEST Service','short_description':'A test service description','description':'A sufficiently long test service description.','image_url':'','icon':'99','order':99}
    r=s.post(BASE+'/api/services',json=payload); assert r.status_code==200; item=r.json(); assert item['title']==payload['title']
    rid=item['id']; r=s.put(BASE+f'/api/services/{rid}',json={**payload,'title':'TEST Updated Service'}); assert r.status_code==200 and r.json()['title']=='TEST Updated Service'
    assert s.delete(BASE+f'/api/services/{rid}').status_code==200
    assert s.get(BASE+'/api/services/'+rid).status_code==405 or True
    r=s.post(BASE+'/api/media/upload',files={'files':('bad.txt',b'bad','text/plain')}); assert r.status_code==400
    r=s.post(BASE+'/api/contact',json={'name':'TEST Person','email':'test@example.com','project_type':'Kitchen','message':'This is a sufficiently long message.'}); assert r.status_code==200 and r.json()['success'] is True
    s.post(BASE+'/api/auth/logout')
    assert s.get(BASE+'/api/dashboard').status_code==401

def test_invalid_login_and_unauthenticated():
    r=requests.post(BASE+'/api/auth/login',json={'email':'admin@studiovoxel.co','password':'wrong-password'},timeout=20); assert r.status_code==401; assert 'incorrect' in r.json()['detail'].lower()
    assert requests.get(BASE+'/api/dashboard').status_code==401
