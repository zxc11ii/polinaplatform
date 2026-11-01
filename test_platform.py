"""Integration checks use a disposable database; real student data is untouched."""
import base64
import contextlib
import http.cookiejar
import importlib.util
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location('studio', Path(__file__).with_name('server.py'))
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class PlatformTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        studio.ROOT = Path(cls.tmp.name)
        studio.DB = studio.ROOT / 'data' / 'test.sqlite'
        studio.initialize()
        with studio.connect() as db:
            db.execute('UPDATE users SET password=?', (studio.password_hash('test-password-123'),))
        cls.server = studio.ThreadingHTTPServer(('127.0.0.1',0),studio.Handler)
        cls.base = 'http://127.0.0.1:'+str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.tmp.cleanup()

    def client(self, login=None):
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        if login:
            self.call(client,'login',{'login':login,'password':'test-password-123'})
        return client

    def call(self, client,path,body=None):
        request = urllib.request.Request(self.base+'/api/'+path, data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with client.open(request) as r:
                return r.status,json.load(r)
        except urllib.error.HTTPError as e:
            return e.code,json.load(e)

    def test_01_auth_and_roles(self):
        self.assertEqual(self.call(self.client(),'dashboard')[0],401)
        student=self.client('alex')
        self.assertEqual(self.call(student,'students',{'name':'No'})[0],403)
        self.assertEqual(self.call(student,'dashboard')[1]['students'],[])
        self.assertEqual(self.call(student,'login',{'login':'alex','password':'wrong'})[0],401)

    def test_02_timing_grading_and_hidden_answers(self):
        student=self.client('alex')
        _,start=self.call(student,'start',{'id':1})
        self.assertNotIn('answer',start['questions'][0])
        self.assertNotIn('explanation',start['questions'][0])
        self.assertEqual(start['attempt']['deadline'],self.call(student,'start',{'id':1})[1]['attempt']['deadline'])
        answers=['goes','were watching','will stay','more interesting','since','is spoken']
        result=self.call(student,'submit',{'id':1,'answers':answers})[1]
        self.assertEqual(result['attempt']['score'],6)
        self.assertIn('explanation',result['questions'][0])
        self.assertEqual(self.call(student,'submit',{'id':1,'answers':[]})[1]['attempt']['score'],6)

    def test_03_teacher_create_assign_isolation(self):
        teacher=self.client('polina'); student=self.client('alex')
        code,new=self.call(teacher,'students',{'name':'Test 5','login':'test5','grade':5})
        self.assertEqual(code,201)
        other=self.client()
        self.assertEqual(self.call(other,'login',{'login':'test5','password':new['password']})[0],200)
        b={'title':'Only fifth grade','description':'test','minutes':1,'grade':5,'questions':[{'prompt':'a?','options':['a','b'],'answer':'a'}]}
        self.assertEqual(self.call(teacher,'assignments',b)[0],201)
        dashboard=self.call(other,'dashboard')[1]
        task=next(a for a in dashboard['assignments'] if a['title']==b['title'])
        self.assertEqual(self.call(student,'start',{'id':task['id']})[0],403)
        _,started=self.call(other,'start',{'id':task['id']})
        with studio.connect() as db:
            db.execute('UPDATE attempts SET deadline=? WHERE id=?',(time.time()-5,started['attempt']['id']))
        expired=self.call(other,'submit',{'id':task['id'],'answers':['a']})[1]
        self.assertEqual(expired['attempt']['score'],0)
        with studio.connect() as db:
            user=db.execute("SELECT id FROM users WHERE login='test5'").fetchone()['id']
        private={'title':'Private PDF','kind':'file','grade':0,'student_id':user,'filename':'test.pdf','file':base64.b64encode(b'%PDF-1.4 test').decode()}
        self.assertEqual(self.call(teacher,'materials',private)[0],201)
        material=self.call(other,'dashboard')[1]['materials'][0]
        self.assertEqual(material['title'],'Private PDF')
        self.assertNotIn('Private PDF',[m['title'] for m in self.call(student,'dashboard')[1]['materials']])
        with other.open(self.base+material['url']) as r:self.assertEqual(r.read(),b'%PDF-1.4 test')
        with self.assertRaises(urllib.error.HTTPError) as cm:student.open(self.base+material['url'])
        self.assertEqual(cm.exception.code,403)
        lesson={'title':'Private lesson','student_id':user,'starts':'2026-11-04T10:00:00+00:00','minutes':60,'url':'https://meet.jit.si/example-lesson'}
        self.assertEqual(self.call(teacher,'lessons',lesson)[0],201)
        self.assertEqual(len(self.call(other,'dashboard')[1]['lessons']),1)
        self.assertEqual(len(self.call(student,'dashboard')[1]['lessons']),0)
        self.assertEqual(self.call(teacher,'reset-password',{'id':user})[0],200)
        self.assertEqual(self.call(other,'dashboard')[0],401)

    def test_04_cross_origin_and_private_files(self):
        client=self.client('polina')
        req=urllib.request.Request(self.base+'/api/students',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://wrong.example'})
        with self.assertRaises(urllib.error.HTTPError) as cm:client.open(req)
        self.assertEqual(cm.exception.code,403)
        for path in ('/data/first-login.txt','/server.py','/../server.py'):
            with self.assertRaises(urllib.error.HTTPError) as cm:client.open(self.base+path)
            self.assertEqual(cm.exception.code,404)

if __name__=='__main__':
    unittest.main(verbosity=2)
