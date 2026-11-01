"""Subject separation for The Lesson Method; preserve existing content as English."""
import json
import time
SUBJECTS={'ru':'Русский язык','en':'Английский язык','de':'Немецкий язык'}


def migrate(db):
    for table,column,definition in [('assignments','subject',"TEXT NOT NULL DEFAULT 'en'"),('materials','subject',"TEXT NOT NULL DEFAULT 'en'"),('courses','subject',"TEXT NOT NULL DEFAULT 'en'"),('lessons','subject',"TEXT NOT NULL DEFAULT 'en'"),('attempts','subject_snapshot',"TEXT NOT NULL DEFAULT 'en'"),('mistakes','subject',"TEXT NOT NULL DEFAULT 'en'")]:
        if column not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


def prepare(db,path,b):
    table=None
    if path in ('/api/assignments','/api/materials','/api/lessons'):table=path.split('/')[-1]
    elif path=='/api/edit-item':table={'assignment':'assignments','material':'materials'}.get(b.get('entity'))
    elif path=='/api/academy/course-save':table='courses'
    if not table:return None
    old=db.execute(f'SELECT * FROM {table} WHERE id=?',(int(b['id']),)).fetchone() if b.get('id') else None
    subject=b.get('subject',old['subject'] if old else 'en')
    if subject not in SUBJECTS:raise ValueError('Некорректный предмет')
    if table=='courses':
        for step in b.get('steps',[]):
            for field,linked in [('material_id','materials'),('assignment_id','assignments')]:
                if step.get(field):
                    row=db.execute(f'SELECT subject FROM {linked} WHERE id=?',(int(step[field]),)).fetchone()
                    if row and row['subject']!=subject:raise ValueError('Материалы курса должны относиться к его предмету')
    return table,subject


def save(db,plan,b):
    if not plan:return
    table,subject=plan
    key=int(b['id']) if b.get('id') else db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute(f'UPDATE {table} SET subject=? WHERE id=?',(subject,key))


def seed(db):
    if db.execute("SELECT 1 FROM academy_meta WHERE key='subjects-tlm-v1'").fetchone():return
    examples=[('ru','Русский язык: пишем грамотно','Орфография',[
        dict(type='choice',prompt='Выбери слово, в котором нужен мягкий знак.',options=['видиш…','горяч…','плащ…'],answer='видиш…',explanation='Во втором лице единственного числа после ш пишется мягкий знак: видишь.'),
        dict(type='text',prompt='Вставь пропущенную букву: ж…раф. Напиши слово полностью.',accepted=['жираф'],explanation='В сочетании жи пишется буква и: жираф.')],
        'Начнём с понятных правил и короткой практики. Объясняй выбор написания и проверяй себя по вопросам.'),
        ('de','Deutsch: первые уверенные шаги','Грамматика немецкого языка',[
        dict(type='choice',prompt='Ich ___ Anna. Выбери верную форму.',options=['heiße','heißt','heißen'],answer='heiße',explanation='С местоимением ich используем форму heiße.'),
        dict(type='text',prompt='Переведи на немецкий: «Спасибо».',accepted=['Danke','danke'],explanation='Danke — спасибо.')],
        'Учимся представляться, замечать формы глаголов и использовать новые слова. Небольшие шаги помогают говорить увереннее.')]
    for subject,title,topic,questions,body in examples:
        for q in questions:q.update(topic=topic,section='',points=1)
        task=db.execute('INSERT INTO assignments(title,description,minutes,grade,questions,created,subject) VALUES(?,?,?,?,?,?,?)',(title+' — практика','Стартовый пример для редактирования преподавателем.',10,0,json.dumps(questions,ensure_ascii=False),time.time(),subject)).lastrowid
        material=db.execute('INSERT INTO materials(title,description,kind,url,grade,created,subject) VALUES(?,?,?,?,?,?,?)',(title+' — памятка','Короткое объяснение перед практикой.','note',body,0,time.time(),subject)).lastrowid
        steps=[dict(key=subject+'-start',title='Поймём правило',body=body,material_id=material,assignment_id=None),dict(key=subject+'-practice',title='Закрепим на практике',body='Реши задания и разберись в объяснениях.',material_id=None,assignment_id=task)]
        db.execute('INSERT INTO courses(title,description,grade,steps,created,subject) VALUES(?,?,?,?,?,?)',(title,'Пример учебного маршрута. Преподаватель может изменить содержание.',0,json.dumps(steps,ensure_ascii=False),time.time(),subject))
    db.execute("INSERT INTO academy_meta VALUES('subjects-tlm-v1','1')")
