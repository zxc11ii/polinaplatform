"""Assignments, immutable attempts, drafts and manual marking."""
import base64
import academy
import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

TIMEZONES=json.loads(Path(__file__).with_name('timezones.json').read_text(encoding='utf-8-sig'))


def migrate(db):
    for table, name, definition in [
        ('users','timezone',"TEXT NOT NULL DEFAULT 'Asia/Yekaterinburg'"),
        ('assignments','archived','INTEGER NOT NULL DEFAULT 0'),
        ('assignments','due','REAL'),('assignments','revision','INTEGER NOT NULL DEFAULT 1'),
        ('materials','archived','INTEGER NOT NULL DEFAULT 0'),
        ('materials','revision','INTEGER NOT NULL DEFAULT 1')]:
        if name not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    if 'number' not in {r['name'] for r in db.execute('PRAGMA table_info(attempts)')}:
        db.execute('''CREATE TABLE attempts_new(id INTEGER PRIMARY KEY, assignment_id INTEGER REFERENCES assignments(id),
            user_id INTEGER REFERENCES users(id), started REAL, deadline REAL, submitted REAL, answers TEXT,
            score REAL, total REAL, number INTEGER NOT NULL DEFAULT 1, snapshot TEXT NOT NULL,
            title_snapshot TEXT NOT NULL, draft TEXT NOT NULL DEFAULT '[]', draft_revision INTEGER NOT NULL DEFAULT 0,
            saved_at REAL, status TEXT NOT NULL DEFAULT 'active', marks TEXT NOT NULL DEFAULT '{}',
            feedback TEXT NOT NULL DEFAULT '', reviewed_at REAL, UNIQUE(assignment_id,user_id,number))''')
        db.execute('''INSERT INTO attempts_new(id,assignment_id,user_id,started,deadline,submitted,answers,score,total,
            snapshot,title_snapshot,draft,status)
            SELECT t.id,t.assignment_id,t.user_id,t.started,t.deadline,t.submitted,t.answers,t.score,t.total,
            a.questions,a.title,COALESCE(t.answers,'[]'),CASE WHEN t.submitted IS NULL THEN 'active' ELSE 'graded' END
            FROM attempts t JOIN assignments a ON a.id=t.assignment_id''')
        db.execute('DROP TABLE attempts'); db.execute('ALTER TABLE attempts_new RENAME TO attempts')
    db.execute('CREATE TABLE IF NOT EXISTS retry_grants(assignment_id INTEGER, user_id INTEGER, extras INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(assignment_id,user_id))')
    db.execute('''CREATE TABLE IF NOT EXISTS assets(url TEXT PRIMARY KEY, owner INTEGER REFERENCES users(id),
        attempt_id INTEGER REFERENCES attempts(id), question_index INTEGER, created REAL, name TEXT)''')


def timestamp(value):
    if value in (None,''): return None
    d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('Нужен часовой пояс')
    return d.timestamp()


def questions_clean(questions, db, user):
    if not isinstance(questions,list) or not 1<=len(questions)<=60: raise ValueError()
    result=[]
    for q in questions:
        kind=q.get('type','choice')
        if kind not in ('choice','text','essay','voice'): raise ValueError()
        prompt=str(q.get('prompt','')).strip()
        if not prompt or len(prompt)>4000: raise ValueError()
        points=int(q.get('points',1 if kind in ('choice','text') else 5))
        if not 1<=points<=20: raise ValueError()
        item=dict(type=kind,prompt=prompt,points=points,explanation=str(q.get('explanation',''))[:4000])
        if kind=='choice':
            options=[str(o).strip()[:500] for o in q['options']]
            if not 2<=len(options)<=6 or not all(options) or len(set(options))!=len(options) or q['answer'] not in options: raise ValueError()
            item.update(options=options,answer=str(q['answer']))
        elif kind=='text':
            answers=[str(a).strip()[:500] for a in q.get('accepted',[]) if str(a).strip()]
            if not answers: raise ValueError()
            item['accepted']=answers[:20]
        audio=str(q.get('audio_url','')).strip()
        if audio:
            if audio.startswith('/uploads/'):
                asset=db.execute('SELECT * FROM assets WHERE url=? AND attempt_id IS NULL',(audio,)).fetchone()
                material=db.execute('SELECT * FROM materials WHERE url=?',(audio,)).fetchone()
                if not asset and not material: raise ValueError()
            elif urlparse(audio).scheme!='https': raise ValueError()
            item['audio_url']=audio
        academy.question_meta(q,item)
        result.append(item)
    return result


def clean_answers(db,attempt,values):
    questions=json.loads(attempt['snapshot'])
    if not isinstance(values,list) or len(values)>len(questions): raise ValueError()
    result=[]
    for i,q in enumerate(questions):
        value=values[i] if i<len(values) else ''
        if not isinstance(value,str): raise ValueError()
        if q.get('type')=='voice' and value:
            if not db.execute('SELECT 1 FROM assets WHERE url=? AND owner=? AND attempt_id=? AND question_index=?',
                (value,attempt['user_id'],attempt['id'],i)).fetchone(): raise ValueError()
        if len(value)>(15000 if q.get('type')=='essay' else 2000): raise ValueError()
        result.append(value)
    return result


def normalized(value): return ' '.join(str(value).strip().casefold().split())


def finish(db,attempt,now):
    if attempt['submitted']: return attempt
    questions=json.loads(attempt['snapshot']); answers=json.loads(attempt['draft'])
    points,total=0,0; pending=False
    for i,q in enumerate(questions):
        kind=q.get('type','choice'); weight=q.get('points',1); total+=weight
        answer=answers[i] if i<len(answers) else ''
        if kind in ('essay','voice'):
            pending=True
        elif normalized(answer) in [normalized(x) for x in (q.get('accepted',[]) if kind=='text' else [q.get('answer','')])]:
            points+=weight
    db.execute('UPDATE attempts SET submitted=?,answers=draft,score=?,total=?,status=? WHERE id=?',
        (now,points,total,'pending' if pending else 'graded',attempt['id']))
    return db.execute('SELECT * FROM attempts WHERE id=?',(attempt['id'],)).fetchone()


def expire(db):
    now=time.time()
    for attempt in db.execute('SELECT * FROM attempts WHERE submitted IS NULL AND deadline<=?',(now,)).fetchall():
        finish(db,attempt,now)


def result(attempt, teacher=False):
    a=dict(attempt); questions=json.loads(a.pop('snapshot'))
    a['rubric_marks']=json.loads(a.get('rubric_marks','{}'))
    a['section_windows']=academy.windows(attempt)
    a['draft']=json.loads(a['draft']); a['marks']=json.loads(a['marks'])
    if not a['submitted'] and not teacher:
        questions=[{k:v for k,v in q.items() if k not in ('answer','accepted','explanation')} for q in questions]
    return dict(title=a['title_snapshot'],questions=questions,attempt=a,serverNow=time.time())


def file_allowed(db, user, path, allowed):
    if user['role']=='teacher': return True
    asset=db.execute('SELECT * FROM assets WHERE url=?',(path,)).fetchone()
    if asset and asset['attempt_id']:
        return asset['owner']==user['id']
    m=db.execute('SELECT * FROM materials WHERE url=? AND archived=0',(path,)).fetchone()
    if m and allowed(m,user): return True
    for row in db.execute('SELECT * FROM assignments WHERE archived=0'):
        if allowed(row,user) and any(q.get('audio_url')==path for q in json.loads(row['questions'])): return True
    for row in db.execute('SELECT snapshot FROM attempts WHERE user_id=?',(user['id'],)):
        if any(q.get('audio_url')==path for q in json.loads(row['snapshot'])): return True
    return False


def dashboard(db,user,allowed):
    expire(db);teacher=user['role']=='teacher'
    tasks=[]
    for row in db.execute('SELECT * FROM assignments ORDER BY id DESC'):
        if not teacher and (row['archived'] or not allowed(row,user)): continue
        a=dict(row);a['count']=len(json.loads(a.pop('questions')))
        grant=db.execute('SELECT extras FROM retry_grants WHERE assignment_id=? AND user_id=?',(a['id'],user['id'])).fetchone()
        a['max_attempts']=1+(grant['extras'] if grant else 0);tasks.append(a)
    materials=[dict(r) for r in db.execute('SELECT * FROM materials ORDER BY id DESC') if teacher or (not r['archived'] and allowed(r,user))]
    lessons=[dict(r) for r in db.execute('SELECT l.*,u.name student_name FROM lessons l JOIN users u ON u.id=l.student_id ORDER BY starts') if teacher or r['student_id']==user['id']]
    attempts=[]
    for row in db.execute('SELECT t.*,u.name student_name FROM attempts t JOIN users u ON u.id=t.user_id ORDER BY t.started DESC,t.id DESC'):
        if not teacher and row['user_id']!=user['id']: continue
        a=dict(row);a.pop('snapshot');a.pop('draft');a['title']=a['title_snapshot'];attempts.append(a)
    students=[dict(r) for r in db.execute("SELECT id,name,login,grade FROM users WHERE role='student'")] if teacher else []
    return dict(user=dict(user),assignments=tasks,materials=materials,lessons=lessons,attempts=attempts,students=students,timezones=TIMEZONES)


def dispatch(db,u,path,b,root,allowed):
    """Return (status, body) or None to use the original account/material routes."""
    if path=='/api/preferences':
        zone=str(b['timezone'])
        if zone not in TIMEZONES: raise ValueError()
        db.execute('UPDATE users SET timezone=? WHERE id=?',(zone,u['id']))
        return 200,{'ok':True}
    if path=='/api/attempt':
        attempt=db.execute('SELECT * FROM attempts WHERE id=?',(int(b['attempt_id']),)).fetchone()
        if not attempt or (u['role']!='teacher' and attempt['user_id']!=u['id']): return 403,{'error':'Нет доступа к попытке'}
        if not attempt['submitted'] and attempt['deadline']<=time.time():attempt=finish(db,attempt,time.time())
        return 200,result(attempt,u['role']=='teacher')
    if path=='/api/start':
        if u['role']!='student': return 403,{'error':'Решение доступно ученикам'}
        a=db.execute('SELECT * FROM assignments WHERE id=?',(int(b['id']),)).fetchone()
        previous=db.execute('SELECT * FROM attempts WHERE assignment_id=? AND user_id=? ORDER BY number DESC LIMIT 1',(int(b['id']),u['id'])).fetchone()
        if previous and not previous['submitted']:
            if previous['deadline']<=time.time():previous=finish(db,previous,time.time())
            return 200,result(previous)
        if not a or not allowed(a,u): return 403,{'error':'Это задание вам не назначено'}
        if a['archived']:return 409,{'error':'Задание в архиве'}
        grant=db.execute('SELECT extras FROM retry_grants WHERE assignment_id=? AND user_id=?',(a['id'],u['id'])).fetchone()
        maximum=1+(grant['extras'] if grant else 0)
        if previous and previous['number']>=maximum:return 200,result(previous)
        now=time.time()
        if a['due'] and now>=a['due']:return 409,{'error':'Срок сдачи закончился. Попросите Полину продлить его.'}
        end=min(now+a['minutes']*60,a['due'] or float('inf'))
        cursor=db.execute('''INSERT INTO attempts(assignment_id,user_id,started,deadline,number,snapshot,title_snapshot)
            VALUES(?,?,?,?,?,?,?)''',(a['id'],u['id'],now,end,previous['number']+1 if previous else 1,a['questions'],a['title']))
        academy.freeze(db,cursor.lastrowid,a)
        return 200,result(db.execute('SELECT * FROM attempts WHERE id=?',(cursor.lastrowid,)).fetchone())
    if path in ('/api/draft','/api/submit','/api/voice-upload'):
        attempt=db.execute('SELECT * FROM attempts WHERE id=? AND user_id=?',(int(b['attempt_id']),u['id'])).fetchone() if b.get('attempt_id') else db.execute('SELECT * FROM attempts WHERE assignment_id=? AND user_id=? ORDER BY number DESC LIMIT 1',(int(b['id']),u['id'])).fetchone()
        if not attempt or u['role']!='student': return 403,{'error':'Нет доступа к попытке'}
        now=time.time()
        if attempt['submitted']:return 200,result(attempt)
        if now>=attempt['deadline']:
            return 200,result(finish(db,attempt,now))
        if path=='/api/voice-upload':
            index=int(b['question_index']);questions=json.loads(attempt['snapshot'])
            if index<0 or index>=len(questions) or questions[index].get('type')!='voice':raise ValueError()
            periods=academy.windows(attempt)
            if periods and not any(w['name']==questions[index].get('section') and w['start']<=now<w['end'] for w in periods):return 409,{'error':'Сейчас нельзя отвечать на этот раздел'}
            url=upload(db,u,b,root,attempt['id'],index)
            draft=json.loads(attempt['draft']);draft+=['']*(len(questions)-len(draft));draft[index]=url
            db.execute('UPDATE attempts SET draft=?,draft_revision=draft_revision+1,saved_at=? WHERE id=?',(json.dumps(draft),now,attempt['id']))
            return 200,{'url':url,**result(db.execute('SELECT * FROM attempts WHERE id=?',(attempt['id'],)).fetchone())}
        if 'answers' in b:
            if int(b.get('revision',attempt['draft_revision']))!=attempt['draft_revision']:
                return 409,{'error':'Ответы изменились в другой вкладке. Откройте попытку заново; текущий текст сохранён на этом устройстве.'}
            answers=clean_answers(db,attempt,b['answers'])
            answers=academy.restricted_answers(attempt,json.loads(attempt['draft']),answers,now)
            db.execute('UPDATE attempts SET draft=?,draft_revision=draft_revision+1,saved_at=? WHERE id=?',(json.dumps(answers,ensure_ascii=False),now,attempt['id']))
            attempt=db.execute('SELECT * FROM attempts WHERE id=?',(attempt['id'],)).fetchone()
        return 200,result(finish(db,attempt,now) if path=='/api/submit' else attempt)
    if u['role']!='teacher':
        if path in ('/api/archive','/api/retry','/api/review','/api/edit-item','/api/asset-upload','/api/item'):return 403,{'error':'Только для преподавателя'}
        return None
    if path=='/api/item':
        table={'assignment':'assignments','material':'materials'}.get(b['entity'])
        if not table:raise ValueError()
        row=db.execute(f'SELECT * FROM {table} WHERE id=?',(int(b['id']),)).fetchone()
        if not row:return 404,{'error':'Запись не найдена'}
        item=dict(row)
        if table=='assignments':item['questions']=json.loads(item['questions'])
        return 200,item
    if path=='/api/archive':
        table={'assignment':'assignments','material':'materials'}.get(b['entity'])
        if not table:raise ValueError()
        if b.get('archived') not in (0,1,False,True):raise ValueError()
        cursor=db.execute(f'UPDATE {table} SET archived=?,revision=revision+1 WHERE id=?',(int(bool(b['archived'])),int(b['id'])))
        return (200,{'ok':True}) if cursor.rowcount else (404,{'error':'Запись не найдена'})
    if path=='/api/retry':
        a=db.execute('SELECT * FROM assignments WHERE id=?',(int(b['id']),)).fetchone()
        s=db.execute("SELECT id,grade FROM users WHERE id=? AND role='student'",(int(b['student_id']),)).fetchone()
        if not a or not s or a['archived'] or not allowed(a,{'id':s['id'],'grade':s['grade'],'role':'student'}):raise ValueError()
        latest=db.execute('SELECT * FROM attempts WHERE assignment_id=? AND user_id=? ORDER BY number DESC LIMIT 1',(a['id'],s['id'])).fetchone()
        if not latest or not latest['submitted']:return 409,{'error':'Сначала ученик должен завершить текущую попытку'}
        if a['due'] and a['due']<=time.time():return 409,{'error':'Сначала продлите срок сдачи в редакторе задания'}
        grant=db.execute('SELECT extras FROM retry_grants WHERE assignment_id=? AND user_id=?',(a['id'],s['id'])).fetchone()
        if grant and 1+grant['extras']>latest['number']:return 409,{'error':'Дополнительная попытка уже разрешена'}
        db.execute('INSERT INTO retry_grants VALUES(?,?,?) ON CONFLICT(assignment_id,user_id) DO UPDATE SET extras=excluded.extras',(a['id'],s['id'],latest['number']))
        return 200,{'ok':True}
    if path=='/api/review':
        attempt=db.execute('SELECT * FROM attempts WHERE id=?',(int(b['attempt_id']),)).fetchone()
        if not attempt or not attempt['submitted']:return 409,{'error':'Попытка ещё не сдана'}
        questions=json.loads(attempt['snapshot']); answers=json.loads(attempt['answers']); marks={};total=0; rubric_marks={}
        for i,q in enumerate(questions):
            if q.get('type') in ('essay','voice'):
                value=b.get('marks',{}).get(str(i))
                if q.get('rubric'):
                    criteria=b.get('rubric_marks',{}).get(str(i),{})
                    for j,r in enumerate(q['rubric']):
                        score=criteria.get(str(j))
                        if not isinstance(score,(int,float)) or not 0<=score<=r['max']:raise ValueError()
                    value=sum(criteria[str(j)] for j in range(len(q['rubric'])))
                    rubric_marks[str(i)]=criteria
                if not isinstance(value,(int,float)) or not 0<=value<=q.get('points',5):raise ValueError()
                marks[str(i)]=value;total+=value
            else:
                accepted=q.get('accepted',[]) if q.get('type')=='text' else [q.get('answer','')]
                if normalized(answers[i] if i<len(answers) else '') in [normalized(x) for x in accepted]:total+=q.get('points',1)
        db.execute("UPDATE attempts SET score=?,marks=?,feedback=?,status='graded',reviewed_at=?,rubric_marks=? WHERE id=?",(total,json.dumps(marks),str(b.get('feedback',''))[:10000],time.time(),json.dumps(rubric_marks),attempt['id']))
        return 200,{'ok':True}
    if path=='/api/asset-upload':return 201,{'url':upload(db,u,b,root)}
    if path in ('/api/assignments','/api/edit-item'):
        entity=b.get('entity','assignment'); table={'assignment':'assignments','material':'materials'}.get(entity)
        if not table:raise ValueError()
        title=str(b['title']).strip()[:200]; grade=int(b.get('grade',0)); student=int(b['student_id']) if b.get('student_id') else None
        if not title or grade not in (0,5,6,7,8,9):raise ValueError()
        if student and not db.execute("SELECT 1 FROM users WHERE id=? AND role='student'",(student,)).fetchone():raise ValueError()
        description=str(b.get('description',''))[:3000]
        if table=='assignments':
            minutes=int(b['minutes'])
            if not 1<=minutes<=180:raise ValueError()
            questions=questions_clean(b['questions'],db,u)
            values=dict(title=title,description=description,minutes=minutes,grade=grade,student_id=student,questions=json.dumps(questions,ensure_ascii=False),due=timestamp(b.get('due')))
        else:
            kind=b['kind'];url=str(b.get('url','')).strip()
            if kind not in ('note','link','video','file') or not url:raise ValueError()
            if kind in ('link','video') and urlparse(url).scheme!='https':raise ValueError()
            if kind=='file':
                old=db.execute('SELECT url FROM materials WHERE id=?',(int(b['id']),)).fetchone()
                asset=db.execute('SELECT 1 FROM assets WHERE url=? AND attempt_id IS NULL',(url,)).fetchone()
                if not asset and (not old or old['url']!=url):raise ValueError()
            values=dict(title=title,description=description,kind=kind,url=url[:15000],grade=grade,student_id=student)
        if path=='/api/edit-item':
            current=db.execute(f'SELECT * FROM {table} WHERE id=?',(int(b['id']),)).fetchone()
            if not current:return 404,{'error':'Запись не найдена'}
            if int(b['revision'])!=current['revision']:return 409,{'error':'Запись изменена в другой вкладке. Откройте редактор заново.'}
            db.execute(f"UPDATE {table} SET "+','.join(k+'=?' for k in values)+',revision=revision+1 WHERE id=?',(*values.values(),current['id']))
        else:
            values['created']=time.time()
            db.execute(f"INSERT INTO {table}("+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
        return 201,{'ok':True}
    return None


def upload(db,user,b,root,attempt_id=None,index=None):
    suffix=Path(str(b['filename'])).suffix.lower()
    supported=('.mp3','.wav','.ogg','.webm','.m4a','.mp4') if attempt_id else ('.pdf','.png','.jpg','.jpeg','.webp','.mp4','.webm','.mp3','.wav','.ogg','.m4a','.docx','.pptx')
    if suffix not in supported:raise ValueError()
    raw=base64.b64decode(b['file'],validate=True)
    if not 1<=len(raw)<=25*1024*1024:raise ValueError()
    filename=secrets.token_hex(16)+suffix;url='/uploads/'+filename
    (root/'uploads'/filename).write_bytes(raw)
    db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',(url,user['id'],attempt_id,index,time.time(),str(b['filename'])[:200]))
    return url
