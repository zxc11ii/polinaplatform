"""Build GitHub Pages preview using ONLY a fresh synthetic database, never local data."""
import importlib.util,json,shutil,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parent.parent
output=Path(sys.argv[1] if len(sys.argv)>1 else root/'_site').resolve();output.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('studio',root/'server.py');studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
with tempfile.TemporaryDirectory() as temp:
    studio.ROOT=Path(temp);studio.DB=studio.ROOT/'data'/'demo.sqlite';studio.initialize()
    with studio.connect() as db:
        now=time.time();questions=json.loads(db.execute('SELECT questions FROM assignments WHERE id=1').fetchone()[0])
        for q in questions:q.update(type='choice',topic='Времена',points=1,section='')
        db.execute('UPDATE assignments SET questions=? WHERE id=1',(json.dumps(questions,ensure_ascii=False),))
        answers=[q['answer'] for q in questions];answers[0]='go';answers[2]='stay'
        db.execute('''INSERT INTO attempts(assignment_id,user_id,started,deadline,submitted,answers,score,total,number,snapshot,title_snapshot,draft,status,academy_frozen)
            VALUES(1,2,?,?,?,?,4,6,1,?,?,?,'graded',1)''',(now-86400,now-85500,now-85900,json.dumps(answers),json.dumps(questions,ensure_ascii=False),'Grammar check: ready, steady, go!',json.dumps(answers)))
        essay=dict(type='essay',topic='Письмо',section='',prompt='Write a short email to your friend about your favourite school subject.',points=5,explanation='Отвечай на вопрос, используй связки и проверь времена.',rubric=[dict(label='Содержание',max=3),dict(label='Язык',max=2)])
        essay_id=db.execute('INSERT INTO assignments(title,description,minutes,grade,questions,created) VALUES(?,?,?,?,?,?)',('Личное письмо: любимый предмет','Пример работы для ручной проверки.',20,9,json.dumps([essay],ensure_ascii=False),now)).lastrowid
        text='Hi Sam! My favourite subject is English. I enjoy reading stories and learning new words. What subjects do you like? Best wishes, Alexandra'
        db.execute('''INSERT INTO attempts(assignment_id,user_id,started,deadline,submitted,answers,score,total,number,snapshot,title_snapshot,draft,status,academy_frozen)
            VALUES(?,?,?,?,?,?,0,5,1,?,?,?,'pending',1)''',(essay_id,2,now-7200,now-6000,now-6600,json.dumps([text]),json.dumps([essay],ensure_ascii=False),'Личное письмо: любимый предмет',json.dumps([text])))
        sections=[dict(name='Чтение',minutes=2),dict(name='Грамматика',minutes=2),dict(name='Письмо',minutes=2)]
        mock_q=[dict(type='choice',topic='Чтение',section='Чтение',prompt='Jane goes to school on foot. How does Jane travel?',options=['She walks','By car','By bus'],answer='She walks',points=1,explanation='On foot — пешком.'),dict(type='text',topic='Времена',section='Грамматика',prompt='Write the past form of see.',accepted=['saw'],points=1,explanation='See — saw — seen.'),{**essay,'section':'Письмо'}]
        db.execute('INSERT INTO assignments(title,description,minutes,grade,questions,created,category,exam_config) VALUES(?,?,?,?,?,?,?,?)',('Короткая репетиция ОГЭ','Демо конструктора: три коротких раздела. Не полный официальный вариант.',6,9,json.dumps(mock_q,ensure_ascii=False),now,'mock',json.dumps(dict(sections=sections),ensure_ascii=False)))
        for title,offset in [('Индивидуальный урок: speaking practice',86400),('Разбираем письмо и вопросы ОГЭ',259200)]:
            db.execute('INSERT INTO lessons(title,starts,minutes,student_id,url,notes) VALUES(?,?,?,?,?,?)',(title,datetime.fromtimestamp(now+offset,timezone.utc).isoformat(),60,2,'https://telemost.yandex.ru/','Демонстрационная запись расписания. Реальная встреча не назначена.'))
        db.execute('INSERT INTO comments(assignment_id,student_id,author_id,question_index,body,created) VALUES(?,?,?,?,?,?)',(1,2,2,0,'Полина, почему после she нужно goes?',now-300))
        studio.academy.sync(db)
        state={table:[dict(r) for r in db.execute('SELECT * FROM '+table)] for table in ('assignments','attempts','materials','lessons','courses','course_reads','vocabulary','word_reviews','comments','notifications','mistakes','retry_grants')}
        state['users']=[dict(r) for r in db.execute('SELECT id,name,login,role,grade,timezone FROM users')]
        state.update(version=1,files={},timezones=studio.learning.TIMEZONES)
for file in (root/'web').iterdir():
    if file.is_file():shutil.copy2(file,output/file.name)
html=(output/'index.html').read_text(encoding='utf-8').replace('href="/','href="./').replace('src="/','src="./')
html=html.replace('<script defer src="./app.js"></script>','<script defer src="./demo-seed.js"></script><script defer src="./demo-api.js"></script><script defer src="./app.js"></script>')
html=html.replace('<script defer src="./academy.js"></script>','<script defer src="./academy.js"></script><link rel="stylesheet" href="./demo.css"><script defer src="./demo-ui.js"></script>')
(output/'index.html').write_text(html,encoding='utf-8')
(output/'demo-seed.js').write_text('window.POLINA_DEMO_SEED = '+json.dumps(state,ensure_ascii=False)+';\n',encoding='utf-8')
for name in ('demo-api.js','demo-ui.js','demo.css'):shutil.copy2(root/'pages-demo'/name,output/name)
(output/'.nojekyll').write_text('',encoding='utf-8')
print('Built interactive demo from synthetic data only.')
