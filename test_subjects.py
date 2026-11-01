import json
import test_academy as baseline
studio=baseline.studio


class SubjectTest(baseline.AcademyTest):
    def test_30_subject_catalog_and_snapshot(self):
        teacher=self.client('polina');student=self.client('alex')
        dashboard=self.call(student,'dashboard')[1]
        self.assertEqual({a['subject'] for a in dashboard['assignments']},{'ru','en','de'})
        self.assertTrue(all(a['subject']=='en' for a in dashboard['assignments'] if a['id']==1))
        de=self.make_task(teacher,subject='de',questions=[dict(type='text',topic='Deutsch',prompt='Danke',accepted=['Danke'])])
        attempt=self.call(student,'start',{'id':de['id']})[1]['attempt']
        self.assertEqual(attempt['subject_snapshot'],'de')
        self.call(student,'submit',{'attempt_id':attempt['id'],'answers':['Danke']})
        self.assertTrue(any(t['topic']=='Deutsch' and t['subject']=='de' for t in self.overview(student)['progress']['topics']))

    def test_31_subject_validation_and_course_links(self):
        teacher=self.client('polina')
        task=self.make_task(teacher,subject='ru')
        wrong=dict(title='Invalid subject',subject='xx',minutes=10,questions=[dict(type='text',prompt='x',accepted=['x'])])
        self.assertEqual(self.call(teacher,'assignments',wrong)[0],400)
        course=dict(title='Russian course',subject='de',grade=9,steps=[dict(title='Step',assignment_id=task['id'])])
        self.assertEqual(self.call(teacher,'academy/course-save',course)[0],400)
        course['subject']='ru'
        self.assertEqual(self.call(teacher,'academy/course-save',course)[0],201)
        stored=next(c for c in self.overview(teacher,student_id=2)['courses'] if c['title']=='Russian course')
        self.assertEqual(stored['subject'],'ru')

    def test_32_error_practice_stays_in_subject(self):
        teacher=self.client('polina');student=self.client('alex')
        for language in ('ru','de'):
            task=self.make_task(teacher,subject=language,questions=[dict(type='text',topic='Общая тема',prompt='Question '+language,accepted=['correct'])])
            a=self.call(student,'start',{'id':task['id']})[1]['attempt']
            self.call(student,'submit',{'attempt_id':a['id'],'answers':['wrong']})
        self.overview(student)
        result=self.call(student,'academy/mistakes-practice',{'subject':'de'})[1]
        a=self.call(student,'start',{'id':result['id']})[1]
        self.assertEqual(a['attempt']['subject_snapshot'],'de')
        self.assertTrue(all('ru' not in q['prompt'] for q in a['questions']))


if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
