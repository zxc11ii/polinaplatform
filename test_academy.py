import json
import time
from datetime import datetime,timezone
import test_learning as baseline
studio=baseline.studio


class AcademyTest(baseline.LearningTest):
    def overview(self,client,**kwargs):
        code,result=self.call(client,'academy/overview',kwargs)
        self.assertEqual(code,200,result);return result

    def test_20_course_progress_and_audience(self):
        teacher=self.client('polina');student=self.client('alex')
        task=self.make_task(teacher,questions=[dict(type='text',topic='Course topic',prompt='Say yes',accepted=['yes'],points=1)])
        course=dict(title='Course test',grade=9,steps=[dict(key='step1',title='Explain',body='Read this',assignment_id=task['id'])])
        self.assertEqual(self.call(teacher,'academy/course-save',course)[0],201)
        saved=next(c for c in self.overview(student)['courses'] if c['title']=='Course test')
        self.assertEqual(saved['completed'],0)
        self.assertEqual(self.call(student,'academy/course-read',{'id':saved['id'],'key':'step1'})[0],200)
        self.assertEqual(next(c for c in self.overview(student)['courses'] if c['id']==saved['id'])['completed'],0)
        a=self.call(student,'start',{'id':task['id']})[1]['attempt']
        self.call(student,'submit',{'attempt_id':a['id'],'answers':['yes']})
        self.assertEqual(next(c for c in self.overview(student)['courses'] if c['id']==saved['id'])['completed'],1)
        self.assertEqual(self.call(student,'academy/course-save',course)[0],403)
        self.call(teacher,'academy/course-archive',{'id':saved['id'],'archived':True})
        self.assertNotIn(saved['id'],[c['id'] for c in self.overview(student)['courses']])
        self.call(teacher,'academy/course-archive',{'id':saved['id'],'archived':False})
        wrong={**course,'title':'Audience mismatch','grade':0}
        self.assertEqual(self.call(teacher,'academy/course-save',wrong)[0],400)

    def test_21_diagnosis_similar_practice_and_resolution(self):
        teacher=self.client('polina');student=self.client('alex')
        topic='Specific diagnostic topic'
        source=self.make_task(teacher,category='diagnostic',questions=[dict(type='text',topic=topic,prompt='First prompt',accepted=['one'],points=1)])
        self.make_task(teacher,questions=[dict(type='text',topic=topic,prompt='Different prompt',accepted=['two'],points=1)])
        a=self.call(student,'start',{'id':source['id']})[1]['attempt']
        self.call(student,'submit',{'attempt_id':a['id'],'answers':['wrong']})
        state=self.overview(student)
        self.assertEqual(next(t for t in state['progress']['topics'] if t['topic']==topic)['percent'],0)
        self.assertTrue(any(d['id']==a['id'] for d in state['progress']['diagnostics']))
        mistake=next(e for e in state['mistakes'] if e['attempt_id']==a['id'])
        practice=self.call(student,'academy/mistakes-practice',{})[1]
        self.assertGreater(practice['novel'],0)
        attempt=self.call(student,'start',{'id':practice['id']})[1]
        self.assertEqual(attempt['attempt']['category_snapshot'],'mistakes')
        with studio.connect() as db:qs=json.loads(db.execute('SELECT snapshot FROM attempts WHERE id=?',(attempt['attempt']['id'],)).fetchone()['snapshot'])
        answers=[q.get('answer',(q.get('accepted') or [''])[0]) for q in qs]
        self.call(student,'submit',{'attempt_id':attempt['attempt']['id'],'answers':answers})
        self.assertNotIn(mistake['id'],[e['id'] for e in self.overview(student)['mistakes']])

    def test_22_vocabulary_schedule_privacy_idempotence(self):
        teacher=self.client('polina');student=self.client('alex')
        self.assertEqual(self.call(teacher,'academy/word-save',dict(student_id=2,word='reliable',translation='надёжный',example='A reliable friend'))[0],201)
        word=next(w for w in self.overview(student)['words'] if w['word']=='reliable')
        event=dict(id=word['id'],known=True,event_id='review-test-unique')
        self.assertEqual(self.call(student,'academy/word-rate',event)[0],200)
        w=next(w for w in self.overview(student)['words'] if w['id']==word['id'])
        self.assertEqual(w['stage'],1);self.assertGreater(w['next_due'],time.time()+85000)
        self.call(student,'academy/word-rate',event)
        self.assertEqual(next(w for w in self.overview(student)['words'] if w['id']==word['id'])['stage'],1)
        self.assertEqual(self.call(teacher,'academy/word-rate',{**event,'student_id':2})[0],403)
        self.assertEqual(self.call(student,'academy/overview',{'student_id':1})[0],403)

    def test_23_mock_section_clocks_and_rubric(self):
        teacher=self.client('polina');student=self.client('alex')
        q=[dict(type='text',topic='Чтение',section='Reading',prompt='First section',accepted=['first'],points=1),dict(type='essay',topic='Письмо',section='Writing',prompt='Write',points=5,rubric=[dict(label='Content',max=3),dict(label='Language',max=2)])]
        task=self.make_task(teacher,minutes=2,category='mock',exam_config={'sections':[{'name':'Reading','minutes':1},{'name':'Writing','minutes':1}]},questions=q)
        attempt=self.call(student,'start',{'id':task['id']})[1]['attempt']
        r=self.call(student,'draft',{'attempt_id':attempt['id'],'answers':['first','not yet']})[1]
        self.assertEqual(r['attempt']['draft'],['first',''])
        with studio.connect() as db:db.execute('UPDATE attempts SET started=? WHERE id=?',(time.time()-70,attempt['id']))
        r=self.call(student,'draft',{'attempt_id':attempt['id'],'answers':['changed','My essay']})[1]
        self.assertEqual(r['attempt']['draft'],['first','My essay'])
        self.call(student,'submit',{'attempt_id':attempt['id']})
        self.assertEqual(self.call(teacher,'review',{'attempt_id':attempt['id'],'marks':{'1':5}})[0],400)
        self.assertEqual(self.call(teacher,'review',{'attempt_id':attempt['id'],'marks':{'1':99},'rubric_marks':{'1':{'0':3,'1':1}},'feedback':'Nice'})[0],200)
        graded=self.call(student,'attempt',{'attempt_id':attempt['id']})[1]
        self.assertEqual(graded['attempt']['score'],5)
        exams=self.overview(student)['progress']['exams']
        record=next(x for x in exams if x['id']==attempt['id'])
        self.assertEqual(record['sections']['Writing']['earned'],4)

    def test_24_private_question_threads(self):
        teacher=self.client('polina');student=self.client('alex');task=self.make_task(teacher)
        post=dict(id=task['id'],question_index=0,body='Can you help me?')
        self.assertEqual(self.call(student,'academy/comment-post',post)[0],200)
        self.assertEqual(self.call(teacher,'academy/comment-post',{**post,'student_id':2,'body':'Yes, try this.'})[0],200)
        thread=self.call(student,'academy/comments',dict(id=task['id'],question_index=0))[1]['comments']
        self.assertEqual(len(thread),2)
        threads=self.call(teacher,'academy/discussions',{})[1]['threads']
        self.assertTrue(any(t['assignment_id']==task['id'] and t['question_index']==0 for t in threads))
        self.assertEqual(self.call(student,'academy/comments',dict(id=task['id'],question_index=0,student_id=1))[0],403)
        notes=self.overview(student)['notifications'];self.assertTrue(any(n['title']=='Ответ Полины' for n in notes))

    def test_25_calendar_notifications(self):
        teacher=self.client('polina');student=self.client('alex')
        soon=datetime.fromtimestamp(time.time()+3600,timezone.utc).isoformat()
        task=self.make_task(teacher,due=soon)
        self.call(teacher,'lessons',dict(title='Calendar test lesson',student_id=2,starts=soon,minutes=60,url='https://example.com/meeting'))
        state=self.overview(student)
        self.assertTrue(any(e['title']=='Calendar test lesson' for e in state['events']))
        self.assertTrue(any(n['title']=='Скоро урок' for n in state['notifications']))
        self.assertTrue(any(n['title']=='Скоро срок сдачи' for n in state['notifications']))
        ics=self.call(student,'academy/calendar-export',{})[1]['ics']
        self.assertIn('BEGIN:VCALENDAR',ics);self.assertIn('Calendar test lesson',ics)
        self.call(student,'academy/read-notifications',{})
        self.assertTrue(all(n['seen'] for n in self.overview(student)['notifications']))


if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
