"""Courses, diagnosis, targeted practice, vocabulary, mock exams and communication."""
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone, timedelta


TOPICS=['Времена','Лексика','Чтение','Аудирование','Письмо','Говорение']
CATEGORIES=('practice','diagnostic','mock','mistakes')


def migrate(db):
    for table,name,definition in [('assignments','category',"TEXT NOT NULL DEFAULT 'practice'"),
        ('assignments','exam_config',"TEXT NOT NULL DEFAULT '{}'"),('assignments','mistake_links',"TEXT NOT NULL DEFAULT '{}'"),
        ('attempts','category_snapshot',"TEXT NOT NULL DEFAULT 'practice'"),('attempts','exam_snapshot',"TEXT NOT NULL DEFAULT '{}'"),
        ('attempts','mistake_links_snapshot',"TEXT NOT NULL DEFAULT '{}'"),('attempts','rubric_marks',"TEXT NOT NULL DEFAULT '{}'"),
        ('attempts','academy_frozen','INTEGER NOT NULL DEFAULT 0')]:
        if name not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    schema=[
        '''CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY,title TEXT NOT NULL,description TEXT,grade INTEGER,student_id INTEGER REFERENCES users(id),steps TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,created REAL)''',
        '''CREATE TABLE IF NOT EXISTS course_reads(user_id INTEGER,course_id INTEGER REFERENCES courses(id),step_key TEXT,read_at REAL,PRIMARY KEY(user_id,course_id,step_key))''',
        '''CREATE TABLE IF NOT EXISTS vocabulary(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),word TEXT NOT NULL,translation TEXT NOT NULL,example TEXT,audio TEXT,next_due REAL,stage INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1)''',
        '''CREATE TABLE IF NOT EXISTS word_reviews(event_id TEXT PRIMARY KEY,word_id INTEGER REFERENCES vocabulary(id),user_id INTEGER,known INTEGER,created REAL)''',
        '''CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,assignment_id INTEGER REFERENCES assignments(id),student_id INTEGER REFERENCES users(id),author_id INTEGER REFERENCES users(id),question_index INTEGER,body TEXT,created REAL)''',
        '''CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),event_key TEXT UNIQUE,title TEXT,body TEXT,page TEXT,created REAL,seen INTEGER NOT NULL DEFAULT 0)''',
        '''CREATE TABLE IF NOT EXISTS mistakes(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),attempt_id INTEGER REFERENCES attempts(id),question_index INTEGER,fingerprint TEXT,topic TEXT,prompt TEXT,resolved INTEGER DEFAULT 0,UNIQUE(attempt_id,question_index))''',
        '''CREATE TABLE IF NOT EXISTS academy_meta(key TEXT PRIMARY KEY,value TEXT)''']
    for sql in schema: db.execute(sql)


def seed(db):
    if db.execute("SELECT 1 FROM academy_meta WHERE key='starter-v3'").fetchone():return
    questions=[
        dict(type='choice',topic='Времена',prompt='She ___ tennis every Saturday.',options=['play','plays','playing'],answer='plays',points=1,explanation='С he/she/it в Present Simple используем -s.'),
        dict(type='text',topic='Времена',prompt='Write the past form of go.',accepted=['went'],points=1,explanation='Go — went — gone.'),
        dict(type='choice',topic='Лексика',prompt='Choose the opposite of expensive.',options=['cheap','large','quiet'],answer='cheap',points=1,explanation='Expensive — дорогой, cheap — дешёвый.'),
        dict(type='text',topic='Лексика',prompt='Translate into English: библиотека.',accepted=['library','a library'],points=1,explanation='Library — библиотека, bookshop — книжный магазин.'),
        dict(type='choice',topic='Чтение',prompt='Tom walks to school. It takes him ten minutes. How does he get to school?',options=['By bus','On foot','By bike'],answer='On foot',points=1,explanation='Walks означает идёт пешком.'),
        dict(type='choice',topic='Чтение',prompt='The museum is closed on Mondays. When can you NOT visit?',options=['Tuesday','Saturday','Monday'],answer='Monday',points=1,explanation='Closed on Mondays — закрыт по понедельникам.')]
    cursor=db.execute("INSERT INTO assignments(title,description,minutes,grade,questions,created,category) VALUES(?,?,?,?,?,?,?)",('Первый шаг: входная диагностика','Короткая стартовая диагностика трёх тем. Авторский пример, не экзамен и не оценка полного уровня языка.',12,0,json.dumps(questions,ensure_ascii=False),time.time(),'diagnostic'))
    diagnostic_id=cursor.lastrowid
    variants=[dict(type='text',topic='Времена',prompt='Write the past form of see.',accepted=['saw'],points=1,explanation='See — saw — seen.'),dict(type='choice',topic='Времена',prompt='My brother ___ English every day.',options=['study','studies','studying'],answer='studies',points=1,explanation='После согласной y меняется на -ies.'),dict(type='text',topic='Лексика',prompt='Translate into English: учитель.',accepted=['teacher','a teacher'],points=1,explanation='Teacher — учитель.'),dict(type='choice',topic='Лексика',prompt='Choose the opposite of difficult.',options=['easy','late','empty'],answer='easy',points=1,explanation='Easy — лёгкий.'),dict(type='choice',topic='Чтение',prompt='Kate takes a bus to the library. How does she travel?',options=['By bus','On foot','By train'],answer='By bus',points=1,explanation='Takes a bus — едет на автобусе.'),dict(type='choice',topic='Чтение',prompt='The shop opens at nine and closes at six. Can you enter at seven in the evening?',options=['Yes','No'],answer='No',points=1,explanation='В семь вечера магазин уже закрыт.')]
    practice_id=db.execute('INSERT INTO assignments(title,description,minutes,grade,questions,created) VALUES(?,?,?,?,?,?)',('Короткие повторения','Авторские упражнения для практики и работы над ошибками.',10,0,json.dumps(variants,ensure_ascii=False),time.time())).lastrowid
    for title,body in [('Времена без путаницы','Present Simple: привычки, расписание, факты. После he/she/it добавляем -s.\nPast Simple: завершённые события в прошлом. Повторяй неправильные глаголы небольшими группами.'),('Аудирование: слушаем с уверенностью','Сначала прочитай вопросы. При первом прослушивании пойми общий смысл, при втором найди детали.\nПолина может добавить аудиоматериалы к этому курсу.'),('Личное письмо: от плана к тексту','Начни с обращения. Ответь на каждый вопрос друга, используй связки и проверь грамматику.\nКритерии и конкретный объём текста задаёт преподаватель в задании.')]:
        steps=[dict(key=secrets.token_hex(8),title='Разбираемся в теме',body=body,material_id=None,assignment_id=None),dict(key=secrets.token_hex(8),title='Переходим к практике',body='Реши задания и посмотри объяснения к ответам.',material_id=None,assignment_id=practice_id if title.startswith('Времена') else None)]
        db.execute('INSERT INTO courses(title,description,grade,steps,created) VALUES(?,?,?,?,?)',(title,'Стартовый пример курса. Полина может изменить и дополнить его.',0,json.dumps(steps,ensure_ascii=False),time.time()))
    for user in db.execute("SELECT id FROM users WHERE role='student'"):
        for word,translation,example in [('confident','уверенный','I feel more confident when I practise.'),('improve','улучшать','I want to improve my English.'),('journey','путешествие; путь','Learning is a journey.')]:
            db.execute('INSERT INTO vocabulary(user_id,word,translation,example,audio,next_due) VALUES(?,?,?,?,?,?)',(user['id'],word,translation,example,'',time.time()))
    db.execute("INSERT INTO academy_meta VALUES('starter-v3','1')")


def fp(q):return hashlib.sha256(json.dumps({k:v for k,v in q.items() if k in ('prompt','type','answer','accepted')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def question_meta(q,item):
    item['topic']=str(q.get('topic','Времена')).strip()[:100] or 'Общая практика'
    item['section']=str(q.get('section','')).strip()[:100]
    rubric=q.get('rubric',[])
    if rubric:
        if item['type'] not in ('essay','voice') or not isinstance(rubric,list) or len(rubric)>10:raise ValueError()
        clean=[dict(label=str(r['label']).strip()[:150],max=int(r['max'])) for r in rubric]
        if not all(r['label'] and 1<=r['max']<=20 for r in clean) or sum(r['max'] for r in clean)!=item['points']:raise ValueError()
        item['rubric']=clean


def config_validate(db,b,learning):
    if b.get('entity','assignment')!='assignment':return None
    current=db.execute('SELECT * FROM assignments WHERE id=?',(int(b['id']),)).fetchone() if b.get('id') else None
    category=b.get('category',current['category'] if current else 'practice')
    if category not in ('practice','diagnostic','mock'):raise ValueError()
    config=b.get('exam_config',json.loads(current['exam_config']) if current else {})
    if category=='mock':
        sections=config.get('sections',[])
        if not isinstance(sections,list) or not 1<=len(sections)<=8:raise ValueError()
        clean=[dict(name=str(s['name']).strip()[:100],minutes=int(s['minutes'])) for s in sections]
        if not all(s['name'] and 1<=s['minutes']<=180 for s in clean) or len({s['name'] for s in clean})!=len(clean):raise ValueError()
        if sum(s['minutes'] for s in clean)!=int(b['minutes']):raise ValueError()
        names={s['name'] for s in clean}
        if not all(q.get('section') in names for q in b['questions']):raise ValueError()
        if names!={q['section'] for q in b['questions']}:raise ValueError()
        config={'sections':clean,'description':str(config.get('description',''))[:3000]}
    else:config={}
    return category,config


def freeze(db,id,a):
    db.execute('UPDATE attempts SET category_snapshot=?,exam_snapshot=?,mistake_links_snapshot=?,subject_snapshot=?,academy_frozen=1 WHERE id=?',
        (a['category'],a['exam_config'],a['mistake_links'],a['subject'],id))


def windows(attempt):
    sections=json.loads(attempt['exam_snapshot']).get('sections',[]);start=attempt['started'];result=[]
    for s in sections:
        end=min(start+s['minutes']*60,attempt['deadline'])
        result.append(dict(name=s['name'],start=start,end=end));start+=s['minutes']*60
    return result


def restricted_answers(attempt,old,new,now):
    periods={s['name']:s for s in windows(attempt)}
    if not periods:return new
    questions=json.loads(attempt['snapshot']);result=[]
    for i,q in enumerate(questions):
        w=periods.get(q.get('section'));previous=old[i] if i<len(old) else ''
        result.append(new[i] if w and w['start']<=now<w['end'] else previous)
    return result


def question_score(q,answer,marks,index):
    if q.get('type') in ('essay','voice'):return float(marks.get(str(index),0))
    accepted=q.get('accepted',[]) if q.get('type')=='text' else [q.get('answer','')]
    normalized=lambda x:' '.join(str(x).casefold().split())
    return q.get('points',1) if normalized(answer) in [normalized(a) for a in accepted] else 0


def notify(db,user,key,title,body='',page='notifications'):
    db.execute('INSERT OR IGNORE INTO notifications(user_id,event_key,title,body,page,created) VALUES(?,?,?,?,?,?)',(user,f'{user}:{key}',title,body,page,time.time()))


def sync(db):
    # Recompute error resolution from immutable attempts, so a corrected teacher mark is respected.
    db.execute('UPDATE mistakes SET resolved=1')
    db.execute('UPDATE mistakes SET subject=(SELECT subject_snapshot FROM attempts WHERE attempts.id=mistakes.attempt_id)')
    outcomes={};links=[]
    for a in db.execute("SELECT * FROM attempts WHERE submitted IS NOT NULL ORDER BY started,id").fetchall():
        if a['status']=='pending':
            for teacher in db.execute("SELECT id FROM users WHERE role='teacher'"):
                notify(db,teacher['id'],'submitted:'+str(a['id']),'Работа ждёт проверки',a['title_snapshot'],'students')
            continue
        if a['reviewed_at']:notify(db,a['user_id'],f"review:{a['id']}:{a['reviewed_at']}",'Полина проверила работу',a['title_snapshot'],'progress')
        qs=json.loads(a['snapshot']);answers=json.loads(a['answers'] or '[]');marks=json.loads(a['marks']);ml=json.loads(a['mistake_links_snapshot'])
        for i,q in enumerate(qs):
            earned=question_score(q,answers[i] if i<len(answers) else '',marks,i);correct=earned>=q.get('points',1);key=(a['user_id'],a['subject_snapshot'],fp(q))
            outcomes[key]=correct
            if not correct:
                db.execute('''INSERT INTO mistakes(user_id,attempt_id,question_index,fingerprint,topic,prompt,resolved,subject) VALUES(?,?,?,?,?,?,0,?)
                    ON CONFLICT(attempt_id,question_index) DO UPDATE SET resolved=0''',(a['user_id'],a['id'],i,key[2],q.get('topic','Времена'),q['prompt'],a['subject_snapshot']))
            if str(i) in ml:links.append((int(ml[str(i)]),correct,a['user_id']))
    for (user,subject,fingerprint),correct in outcomes.items():
        if correct:db.execute('UPDATE mistakes SET resolved=1 WHERE user_id=? AND subject=? AND fingerprint=?',(user,subject,fingerprint))
    for id,correct,user in links:
        if correct:db.execute('UPDATE mistakes SET resolved=1 WHERE id=? AND user_id=?',(id,user))


def stats(db,user):
    topics={};exams=[];diagnostic=[]
    for a in db.execute("SELECT * FROM attempts WHERE user_id=? AND status='graded' ORDER BY started,id",(user,)):
        qs=json.loads(a['snapshot']);answers=json.loads(a['answers'] or '[]');marks=json.loads(a['marks']);sections={}
        per={}
        for i,q in enumerate(qs):
            topic=q.get('topic','Времена');earned=question_score(q,answers[i] if i<len(answers) else '',marks,i);maximum=q.get('points',1)
            row=per.setdefault(topic,dict(earned=0,total=0));row['earned']+=earned;row['total']+=maximum
            sec=sections.setdefault(q.get('section') or 'Практика',dict(earned=0,total=0));sec['earned']+=earned;sec['total']+=maximum
        for topic,row in per.items():topics.setdefault((a['subject_snapshot'],topic),[]).append({**row,'attempt':a['id'],'date':a['submitted']})
        if a['category_snapshot']=='diagnostic':diagnostic.append(dict(id=a['id'],title=a['title_snapshot'],topics=per,date=a['submitted'],subject=a['subject_snapshot']))
        if a['category_snapshot']=='mock':exams.append(dict(id=a['id'],title=a['title_snapshot'],score=a['score'],total=a['total'],sections=sections,date=a['submitted'],subject=a['subject_snapshot']))
    result=[]
    for (subject,topic),history in topics.items():
        recent=history[-5:];total=sum(r['total'] for r in recent);earned=sum(r['earned'] for r in recent)
        result.append(dict(subject=subject,topic=topic,percent=round(earned/total*100) if total else 0,evidence=len(history),history=history))
    result.sort(key=lambda x:x['percent'])
    return dict(topics=result,diagnostics=diagnostic,exams=exams)


def schedule(db,user,allowed):
    teacher=user['role']=='teacher';events=[]
    for row in db.execute('SELECT l.*,u.name student_name FROM lessons l JOIN users u ON u.id=l.student_id'):
        if teacher or row['student_id']==user['id']:
            events.append(dict(id='lesson-'+str(row['id']),title=row['title'],date=row['starts'],kind='lesson',minutes=row['minutes'],url=row['url'],student=row['student_name']))
    for row in db.execute('SELECT * FROM assignments WHERE archived=0 AND due IS NOT NULL'):
        if teacher or allowed(row,user):events.append(dict(id='task-'+str(row['id']),title=row['title'],date=datetime.fromtimestamp(row['due'],timezone.utc).isoformat(),kind='task',assignment_id=row['id'],minutes=1))
    return sorted(events,key=lambda x:datetime.fromisoformat(x['date'].replace('Z','+00:00')).timestamp())


def reminders(db,user,allowed):
    now=time.time()
    for event in schedule(db,user,allowed):
        when=datetime.fromisoformat(event['date'].replace('Z','+00:00')).timestamp()
        if now<=when<=now+86400:
            if event['kind']=='task' and db.execute('SELECT 1 FROM attempts WHERE user_id=? AND assignment_id=? AND submitted IS NOT NULL',(user['id'],event['assignment_id'])).fetchone():continue
            notify(db,user['id'],'reminder:'+event['id']+':'+str(when),'Скоро урок' if event['kind']=='lesson' else 'Скоро срок сдачи',event['title'],'calendar')
    due=db.execute('SELECT COUNT(*) FROM vocabulary WHERE user_id=? AND archived=0 AND next_due<=?',(user['id'],now)).fetchone()[0]
    if due:notify(db,user['id'],'words:'+time.strftime('%Y-%m-%d',time.gmtime(now)),'Пора повторить слова',f'Карточек к повторению: {due}','words')


def can_course(row,user,allowed):return not row['archived'] and allowed(row,user)


def course_view(db,row,user,allowed,teacher_view=False):
    c=dict(row);steps=json.loads(c['steps']);read={r['step_key'] for r in db.execute('SELECT step_key FROM course_reads WHERE user_id=? AND course_id=?',(user['id'],row['id']))}
    for s in steps:
        s['read']=s['key'] in read;s['complete']=s['read']
        for key,table in [('material_id','materials'),('assignment_id','assignments')]:
            if s.get(key):
                linked=db.execute(f'SELECT * FROM {table} WHERE id=?',(s[key],)).fetchone()
                if not linked or (not teacher_view and user['role']!='teacher' and (linked['archived'] or not allowed(linked,user))):
                    s[key]=None;s['unavailable']=True;s['complete']=False
        if s.get('assignment_id'):
            done=db.execute("SELECT * FROM attempts WHERE user_id=? AND assignment_id=? AND status='graded' ORDER BY number DESC LIMIT 1",(user['id'],s['assignment_id'])).fetchone()
            s['complete']=s['read'] and bool(done and done['total'] and done['score']/done['total']>=.6)
    c['steps']=steps;c['completed']=sum(s['complete'] for s in steps);c['count']=len(steps)
    return c


def overview(db,user,target,allowed):
    sync(db);reminders(db,user,allowed)
    profile=stats(db,target)
    target_user=db.execute('SELECT id,role,grade FROM users WHERE id=?',(target,)).fetchone()
    courses=[course_view(db,r,target_user,allowed,user['role']=='teacher') for r in db.execute('SELECT * FROM courses ORDER BY id DESC') if user['role']=='teacher' or can_course(r,user,allowed)]
    words=[dict(r) for r in db.execute('SELECT * FROM vocabulary WHERE user_id=? AND archived=0 ORDER BY next_due,id',(target,))]
    errors=[dict(r) for r in db.execute('SELECT * FROM mistakes WHERE user_id=? AND resolved=0 ORDER BY id DESC',(target,))]
    notes=[dict(r) for r in db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100',(user['id'],))]
    return dict(courses=courses,words=words,mistakes=errors,progress=profile,notifications=notes,events=schedule(db,user,allowed),target=target,viewer=user['id'])


def audience(db,b):
    grade=int(b.get('grade',0));student=int(b['student_id']) if b.get('student_id') else None
    if grade not in (0,5,6,7,8,9):raise ValueError()
    if student and not db.execute("SELECT 1 FROM users WHERE id=? AND role='student'",(student,)).fetchone():raise ValueError()
    return grade,student


def dispatch(db,user,path,b,root,allowed,learning):
    if not path.startswith('/api/academy/'):return None
    route=path.removeprefix('/api/academy/');teacher=user['role']=='teacher'
    target=int(b.get('student_id') or user['id'])
    if target!=user['id'] and (not teacher or not db.execute("SELECT 1 FROM users WHERE id=? AND role='student'",(target,)).fetchone()):return 403,{'error':'Нет доступа к ученику'}
    learning.expire(db)
    if route=='overview':return 200,overview(db,user,target,allowed)
    if route=='read-notifications':
        db.execute('UPDATE notifications SET seen=1 WHERE user_id=?',(user['id'],));return 200,{'ok':True}
    if route in ('course-save','course-archive'):
        if not teacher:return 403,{'error':'Только для преподавателя'}
        if route=='course-archive':
            db.execute('UPDATE courses SET archived=?,revision=revision+1 WHERE id=?',(int(bool(b['archived'])),int(b['id'])));return 200,{'ok':True}
        title=str(b['title']).strip()[:200];grade,student=audience(db,b);steps=b['steps']
        if not title or not isinstance(steps,list) or not 1<=len(steps)<=50:raise ValueError()
        clean=[];keys=set()
        for s in steps:
            key=str(s.get('key') or secrets.token_hex(8))
            if key in keys:raise ValueError()
            keys.add(key);step=dict(key=key,title=str(s['title']).strip()[:200],body=str(s.get('body',''))[:15000])
            if not step['title']:raise ValueError()
            for k,table in [('material_id','materials'),('assignment_id','assignments')]:
                step[k]=int(s[k]) if s.get(k) else None
                if step[k]:
                    row=db.execute(f'SELECT * FROM {table} WHERE id=? AND archived=0',(step[k],)).fetchone()
                    if not row:raise ValueError()
                    if student:
                        recipient=db.execute('SELECT * FROM users WHERE id=?',(student,)).fetchone()
                        if not allowed(row,recipient):return 400,{'error':'Материал или задание не доступно выбранному ученику'}
                    elif row['student_id'] or row['grade'] not in (0,grade):return 400,{'error':'Аудитория курса шире аудитории связанного задания/материала'}
            clean.append(step)
        if b.get('id'):
            old=db.execute('SELECT * FROM courses WHERE id=?',(int(b['id']),)).fetchone()
            if not old or old['revision']!=int(b['revision']):return 409,{'error':'Курс изменился. Откройте редактор заново.'}
            db.execute('UPDATE courses SET title=?,description=?,grade=?,student_id=?,steps=?,revision=revision+1 WHERE id=?',(title,str(b.get('description',''))[:3000],grade,student,json.dumps(clean,ensure_ascii=False),old['id']))
        else:db.execute('INSERT INTO courses(title,description,grade,student_id,steps,created) VALUES(?,?,?,?,?,?)',(title,str(b.get('description',''))[:3000],grade,student,json.dumps(clean,ensure_ascii=False),time.time()))
        return 201,{'ok':True}
    if route=='course-read':
        c=db.execute('SELECT * FROM courses WHERE id=?',(int(b['id']),)).fetchone()
        if not c or not can_course(c,user,allowed):return 403,{'error':'Нет доступа к курсу'}
        if str(b['key']) not in {s['key'] for s in json.loads(c['steps'])}:raise ValueError()
        db.execute('INSERT OR IGNORE INTO course_reads VALUES(?,?,?,?)',(user['id'],c['id'],str(b['key']),time.time()));return 200,{'ok':True}
    if route in ('word-save','word-archive','word-rate'):
        if route=='word-save':
            if teacher and target==user['id']:return 400,{'error':'Выберите ученика'}
            word=str(b['word']).strip()[:200];translation=str(b['translation']).strip()[:500];audio=str(b.get('audio','')).strip()
            if not word or not translation:raise ValueError()
            if audio and not audio.startswith('https://'):raise ValueError()
            if b.get('id'):
                row=db.execute('SELECT * FROM vocabulary WHERE id=? AND user_id=?',(int(b['id']),target)).fetchone()
                if not row:return 403,{'error':'Нет доступа к слову'}
                db.execute('UPDATE vocabulary SET word=?,translation=?,example=?,audio=?,revision=revision+1 WHERE id=?',(word,translation,str(b.get('example',''))[:2000],audio,row['id']))
            else:db.execute('INSERT INTO vocabulary(user_id,word,translation,example,audio,next_due) VALUES(?,?,?,?,?,?)',(target,word,translation,str(b.get('example',''))[:2000],audio,time.time()))
            return 201,{'ok':True}
        row=db.execute('SELECT * FROM vocabulary WHERE id=?',(int(b['id']),)).fetchone()
        if not row or row['user_id']!=target or (not teacher and target!=user['id']):return 403,{'error':'Нет доступа к слову'}
        if route=='word-archive':db.execute('UPDATE vocabulary SET archived=1 WHERE id=?',(row['id'],));return 200,{'ok':True}
        if teacher:return 403,{'error':'Отметку о повторении ставит ученик'}
        event=str(b['event_id'])[:100]
        if db.execute('SELECT 1 FROM word_reviews WHERE event_id=?',(event,)).fetchone():return 200,{'ok':True}
        known=bool(b['known']);stage=min(5,row['stage']+1) if known else 0
        delta=[1,3,7,14,30][min(stage-1,4)]*86400 if known else 600
        db.execute('INSERT INTO word_reviews VALUES(?,?,?,?,?)',(event,row['id'],user['id'],int(known),time.time()))
        db.execute('UPDATE vocabulary SET stage=?,next_due=? WHERE id=?',(stage,time.time()+delta,row['id']));return 200,{'ok':True}
    if route=='mistakes-practice':
        if teacher:return 403,{'error':'Тренировку запускает ученик'}
        sync(db)
        subject=b.get('subject') or (db.execute('SELECT subject FROM mistakes WHERE user_id=? AND resolved=0 ORDER BY id DESC LIMIT 1',(user['id'],)).fetchone() or {'subject':'en'})['subject']
        errors=db.execute('SELECT * FROM mistakes WHERE user_id=? AND resolved=0 AND subject=? ORDER BY id DESC LIMIT 6',(user['id'],subject)).fetchall()
        if not errors:return 409,{'error':'Нет ошибок для повторения'}
        pool=[]
        for a in db.execute("SELECT * FROM assignments WHERE archived=0 AND category IN ('practice','diagnostic')"):
            if allowed(a,user) and a['subject']==subject:pool.extend(json.loads(a['questions']))
        selected=[];links={};used=set();novel=0
        for error in errors:
            alternatives=[q for q in pool if q.get('topic','Времена')==error['topic'] and fp(q)!=error['fingerprint'] and fp(q) not in used and q.get('type','choice') in ('choice','text')]
            if alternatives:q=dict(secrets.choice(alternatives));novel+=1
            else:
                source=db.execute('SELECT snapshot FROM attempts WHERE id=?',(error['attempt_id'],)).fetchone();q=dict(json.loads(source['snapshot'])[error['question_index']])
            used.add(fp(q));links[str(len(selected))]=error['id'];selected.append(q)
        cursor=db.execute("INSERT INTO assignments(title,description,minutes,grade,student_id,questions,created,category,mistake_links) VALUES(?,?,?,?,?,?,?,?,?)",('Папка ошибок — практика','Похожие задания: '+str(novel)+'. Остальные — повторение исходных.',15,user['grade'],user['id'],json.dumps(selected,ensure_ascii=False),time.time(),'mistakes',json.dumps(links)))
        db.execute('UPDATE assignments SET subject=? WHERE id=?',(subject,cursor.lastrowid))
        return 201,{'id':cursor.lastrowid,'novel':novel}
    if route in ('comments','comment-post'):
        assignment=db.execute('SELECT * FROM assignments WHERE id=?',(int(b['id']),)).fetchone()
        if teacher and target==user['id']:return 400,{'error':'Выберите ученика'}
        recipient=db.execute('SELECT * FROM users WHERE id=?',(target,)).fetchone()
        prior=db.execute('SELECT 1 FROM attempts WHERE assignment_id=? AND user_id=?',(int(b['id']),target)).fetchone()
        if not assignment or not recipient or (not allowed(assignment,recipient) and not prior):return 403,{'error':'Нет доступа к обсуждению'}
        index=int(b.get('question_index',-1))
        size=len(json.loads(assignment['questions']))
        for snapshot in db.execute('SELECT snapshot FROM attempts WHERE assignment_id=? AND user_id=?',(assignment['id'],target)):
            size=max(size,len(json.loads(snapshot['snapshot'])))
        if not -1<=index<size:raise ValueError()
        if route=='comment-post':
            body=str(b['body']).strip()
            if not 1<=len(body)<=3000:raise ValueError()
            cursor=db.execute('INSERT INTO comments(assignment_id,student_id,author_id,question_index,body,created) VALUES(?,?,?,?,?,?)',(assignment['id'],target,user['id'],index,body,time.time()))
            receivers=[target] if teacher else [r['id'] for r in db.execute("SELECT id FROM users WHERE role='teacher'")]
            for receiver in receivers:notify(db,receiver,'comment:'+str(cursor.lastrowid),'Ответ Полины' if teacher else 'Вопрос ученика',assignment['title'],'discussions')
        rows=[dict(r) for r in db.execute('SELECT c.*,u.name author_name FROM comments c JOIN users u ON u.id=c.author_id WHERE assignment_id=? AND student_id=? AND question_index=? ORDER BY created,id',(assignment['id'],target,index))]
        return 200,{'comments':rows}
    if route=='discussions':
        query='''SELECT c.assignment_id,c.student_id,c.question_index,a.title,u.name student_name,MAX(c.created) last_at,COUNT(*) count
            FROM comments c JOIN assignments a ON a.id=c.assignment_id JOIN users u ON u.id=c.student_id'''
        args=()
        if not teacher:query+=' WHERE c.student_id=?';args=(user['id'],)
        query+=' GROUP BY c.assignment_id,c.student_id,c.question_index ORDER BY last_at DESC'
        return 200,{'threads':[dict(r) for r in db.execute(query,args)]}
    if route=='calendar-export':
        escape=lambda v:str(v).replace('\\','\\\\').replace('\n','\\n').replace('\r','').replace(',','\\,').replace(';','\\;')
        rows=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Polina Studio//Calendar//RU']
        for e in schedule(db,user,allowed):
            d=datetime.fromisoformat(e['date'].replace('Z','+00:00')).astimezone(timezone.utc)
            rows+=['BEGIN:VEVENT','UID:'+e['id']+'-'+str(user['id'])+'@polina.local','DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),'DTSTART:'+d.strftime('%Y%m%dT%H%M%SZ'),'DTEND:'+(d+timedelta(minutes=e['minutes'])).strftime('%Y%m%dT%H%M%SZ'),'SUMMARY:'+escape(e['title']),'DESCRIPTION:'+escape('Урок' if e['kind']=='lesson' else 'Срок сдачи задания'),'END:VEVENT']
        rows+=['END:VCALENDAR']
        folded=[]
        for line in rows:
            current=''
            for char in line:
                if len((current+char).encode('utf-8'))>73:
                    folded.append(current);current=' '+char
                else:current+=char
            folded.append(current)
        return 200,{'ics':'\r\n'.join(folded)+'\r\n'}
    return 404,{'error':'Раздел не найден'}
