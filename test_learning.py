"""Regression coverage for learning workflows, always on disposable databases."""
import base64
import concurrent.futures
import io
import json
import time
import urllib.error
import wave
from datetime import datetime, timezone
import test_platform as baseline
studio=baseline.studio


class LearningTest(baseline.PlatformTest):
    def make_task(self, teacher, **values):
        body=dict(title='Learning '+str(time.time_ns()),description='Test',minutes=15,grade=9,
            questions=[{'type':'text','prompt':'Write the verb','accepted':['goes','walks'],'points':2}])
        body.update(values)
        code,payload=self.call(teacher,'assignments',body)
        self.assertEqual(code,201,payload)
        return next(a for a in self.call(teacher,'dashboard')[1]['assignments'] if a['title']==body['title'])

    def wav(self):
        out=io.BytesIO()
        with wave.open(out,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*800)
        return base64.b64encode(out.getvalue()).decode()

    def test_10_edit_snapshot_conflict_archive(self):
        teacher=self.client('polina');student=self.client('alex')
        a=self.make_task(teacher)
        attempt=self.call(student,'start',{'id':a['id']})[1]
        item=self.call(teacher,'item',{'id':a['id'],'entity':'assignment'})[1]
        item.update(entity='assignment',questions=[dict(type='text',prompt='Changed',accepted=['new'])],title='Edited')
        self.assertEqual(self.call(teacher,'edit-item',item)[0],201)
        self.assertEqual(self.call(teacher,'edit-item',item)[0],409)
        reopened=self.call(student,'attempt',{'attempt_id':attempt['attempt']['id']})[1]
        self.assertEqual(reopened['questions'][0]['prompt'],'Write the verb')
        self.assertNotIn('accepted',reopened['questions'][0])
        self.assertEqual(self.call(teacher,'archive',{'entity':'assignment','id':a['id'],'archived':1})[0],200)
        self.assertNotIn(a['id'],[x['id'] for x in self.call(student,'dashboard')[1]['assignments']])
        self.assertEqual(self.call(student,'submit',{'attempt_id':attempt['attempt']['id'],'answers':[' GOES ']})[1]['attempt']['score'],2)
        self.assertEqual(self.call(teacher,'archive',{'entity':'assignment','id':a['id'],'archived':0})[0],200)

    def test_11_server_draft_expiry_and_revision(self):
        teacher=self.client('polina');student=self.client('alex');a=self.make_task(teacher)
        r=self.call(student,'start',{'id':a['id']})[1];attempt_id=r['attempt']['id']
        saved=self.call(student,'draft',{'attempt_id':attempt_id,'revision':0,'answers':['Goes']})[1]
        self.assertEqual(saved['attempt']['draft'],['Goes'])
        self.assertEqual(self.call(student,'draft',{'attempt_id':attempt_id,'revision':0,'answers':['bad']})[0],409)
        another=self.client('alex')
        self.assertEqual(self.call(another,'attempt',{'attempt_id':attempt_id})[1]['attempt']['draft'],['Goes'])
        with studio.connect() as db:db.execute('UPDATE attempts SET deadline=? WHERE id=?',(time.time()-3,attempt_id))
        submitted=self.call(another,'submit',{'attempt_id':attempt_id,'answers':['wrong']})[1]
        self.assertEqual(submitted['attempt']['score'],2)
        self.assertEqual(json.loads(submitted['attempt']['answers']),['Goes'])

    def test_12_deadlines_and_timezone(self):
        teacher=self.client('polina');student=self.client('alex')
        a=self.make_task(teacher,due=datetime.fromtimestamp(time.time()-60,timezone.utc).isoformat())
        self.assertEqual(self.call(student,'start',{'id':a['id']})[0],409)
        a=self.make_task(teacher,due=datetime.fromtimestamp(time.time()+60,timezone.utc).isoformat())
        r=self.call(student,'start',{'id':a['id']})[1]
        self.assertAlmostEqual(r['attempt']['deadline'],a['due'])
        self.assertEqual(self.call(teacher,'preferences',{'timezone':'Europe/Moscow'})[0],200)
        self.assertEqual(self.call(teacher,'me')[1]['timezone'],'Europe/Moscow')
        self.assertEqual(self.call(teacher,'preferences',{'timezone':'Fake/Zone'})[0],400)
        self.assertEqual(self.call(teacher,'dashboard')[1]['lessons'],self.call(teacher,'dashboard')[1]['lessons'])

    def test_13_voice_essay_review_retry_and_file_access(self):
        teacher=self.client('polina');student=self.client('alex')
        source=self.call(teacher,'asset-upload',{'filename':'listen.wav','file':self.wav()})[1]['url']
        q=[dict(type='text',prompt='Listen and write',accepted=['yes'],audio_url=source,points=2),dict(type='essay',prompt='Write an email',points=5),dict(type='voice',prompt='Tell me about school',points=4)]
        a=self.make_task(teacher,student_id=2,questions=q)
        attempt=self.call(student,'start',{'id':a['id']})[1]['attempt']
        upload=self.call(student,'voice-upload',{'attempt_id':attempt['id'],'question_index':2,'filename':'answer.wav','file':self.wav()})[1]
        voice=upload['url']
        self.assertEqual(self.call(student,'voice-upload',{'attempt_id':attempt['id'],'question_index':0,'filename':'wrong.wav','file':self.wav()})[0],400)
        submitted=self.call(student,'submit',{'attempt_id':attempt['id'],'revision':upload['attempt']['draft_revision'],'answers':['yes','My email',voice]})[1]
        self.assertEqual(submitted['attempt']['status'],'pending')
        self.assertEqual(submitted['attempt']['score'],2)
        self.assertEqual(self.call(student,'review',{'attempt_id':attempt['id'],'marks':{'1':5,'2':4}})[0],403)
        self.assertEqual(self.call(teacher,'review',{'attempt_id':attempt['id'],'marks':{'1':10,'2':4}})[0],400)
        self.assertEqual(self.call(teacher,'review',{'attempt_id':attempt['id'],'marks':{'1':4,'2':3},'feedback':'Great work'})[0],200)
        graded=self.call(student,'attempt',{'attempt_id':attempt['id']})[1]
        self.assertEqual(graded['attempt']['score'],9)
        self.assertEqual(graded['attempt']['feedback'],'Great work')
        self.assertEqual(self.call(student,'start',{'id':a['id']})[1]['attempt']['id'],attempt['id'])
        self.assertEqual(self.call(teacher,'retry',{'id':a['id'],'student_id':2})[0],200)
        self.assertEqual(self.call(teacher,'retry',{'id':a['id'],'student_id':2})[0],409)
        next_attempt=self.call(student,'start',{'id':a['id']})[1]['attempt']
        self.assertEqual(next_attempt['number'],2)
        self.assertNotEqual(next_attempt['id'],attempt['id'])
        self.assertEqual(self.call(student,'submit',{'attempt_id':next_attempt['id'],'answers':['yes','Text',voice]})[0],400)
        credentials=self.call(teacher,'students',{'name':'Other','login':'voice_other','grade':9})[1]
        other=self.client();self.call(other,'login',{'login':'voice_other','password':credentials['password']})
        self.assertEqual(self.call(other,'attempt',{'attempt_id':attempt['id']})[0],403)
        for path in (voice,source):
            with self.assertRaises(urllib.error.HTTPError) as error:other.open(self.base+path)
            self.assertEqual(error.exception.code,403)
        with student.open(self.base+voice) as response:self.assertTrue(response.read().startswith(b'RIFF'))
        request=__import__('urllib.request',fromlist=['Request']).Request(self.base+source,headers={'Range':'bytes=0-3'})
        with student.open(request) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),b'RIFF')

    def test_14_material_edit_archive_and_missing_records(self):
        teacher=self.client('polina');student=self.client('alex')
        self.call(teacher,'materials',{'title':'Original note','kind':'note','url':'First','grade':9})
        item=next(x for x in self.call(teacher,'dashboard')[1]['materials'] if x['title']=='Original note')
        item.update(entity='material',url='Edited text')
        self.assertEqual(self.call(teacher,'edit-item',item)[0],201)
        self.assertEqual(self.call(teacher,'edit-item',item)[0],409)
        self.call(teacher,'archive',{'entity':'material','id':item['id'],'archived':1})
        self.assertNotIn(item['id'],[x['id'] for x in self.call(student,'dashboard')[1]['materials']])
        self.assertEqual(self.call(student,'item',{'entity':'material','id':item['id']})[0],403)
        self.assertEqual(self.call(teacher,'archive',{'entity':'material','id':999999,'archived':1})[0],404)

    def test_15_concurrent_start_creates_one_attempt(self):
        teacher=self.client('polina');a=self.make_task(teacher)
        clients=[self.client('alex') for _ in range(4)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda c:self.call(c,'start',{'id':a['id']}),clients))
        self.assertEqual(len({r[1]['attempt']['id'] for r in results}),1)


if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
