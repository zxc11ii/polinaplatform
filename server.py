"""Polina English Studio. Python 3.11+, no external dependencies."""
import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import socket
import sqlite3
import time
import learning
import academy
import subjects
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'studio.sqlite'
COOKIE_SECURE = os.environ.get('COOKIE_SECURE') == '1'


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    db = sqlite3.connect(DB, timeout=15, factory=Connection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def password_hash(password):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def password_ok(password, stored):
    salt, digest = stored.split(':')
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, digest)


def initialize():
    DB.parent.mkdir(exist_ok=True)
    (ROOT / 'uploads').mkdir(exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, login TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL, role TEXT NOT NULL, grade INTEGER DEFAULT 9);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id), expires REAL);
        CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY, title TEXT, description TEXT, minutes INTEGER,
          grade INTEGER, student_id INTEGER REFERENCES users(id), questions TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, assignment_id INTEGER REFERENCES assignments(id),
          user_id INTEGER REFERENCES users(id), started REAL, deadline REAL, submitted REAL, answers TEXT,
          score INTEGER, total INTEGER, UNIQUE(assignment_id,user_id));
        CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, title TEXT, description TEXT, kind TEXT,
          url TEXT, grade INTEGER, student_id INTEGER REFERENCES users(id), created REAL);
        CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, title TEXT, starts TEXT, minutes INTEGER,
          student_id INTEGER REFERENCES users(id), url TEXT, notes TEXT);
        CREATE TABLE IF NOT EXISTS login_limits(ip TEXT PRIMARY KEY, count INTEGER, until REAL);
        ''')
        if not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            teacher = secrets.token_urlsafe(12)
            student = secrets.token_urlsafe(10)
            db.execute('INSERT INTO users VALUES(1,?,?,?,?,?)', ('Полина Каменских', 'polina', password_hash(teacher), 'teacher', 9))
            db.execute('INSERT INTO users VALUES(2,?,?,?,?,?)', ('Александра', 'alex', password_hash(student), 'student', 9))
            questions = [
                {'prompt': 'My sister usually ___ to school by bus.', 'options': ['go', 'goes', 'going', 'gone'], 'answer': 'goes', 'explanation': 'В Present Simple к глаголу после she/he/it добавляем -s.'},
                {'prompt': 'We ___ a film when the phone rang.', 'options': ['watch', 'watched', 'were watching', 'have watched'], 'answer': 'were watching', 'explanation': 'Действие в процессе в прошлом: Past Continuous.'},
                {'prompt': 'If it rains tomorrow, we ___ at home.', 'options': ['stay', 'will stay', 'stayed', 'would stay'], 'answer': 'will stay', 'explanation': 'First Conditional: If + Present Simple, will + verb.'},
                {'prompt': 'This book is ___ than the last one.', 'options': ['interesting', 'most interesting', 'more interesting', 'interest'], 'answer': 'more interesting', 'explanation': 'Сравнительная степень длинных прилагательных: more + adjective.'},
                {'prompt': 'I have lived here ___ 2020.', 'options': ['for', 'since', 'during', 'from'], 'answer': 'since', 'explanation': 'Since указывает на начальную точку периода.'},
                {'prompt': 'English ___ in many countries.', 'options': ['speaks', 'is spoken', 'is speaking', 'spoke'], 'answer': 'is spoken', 'explanation': 'Пассивный залог: be + past participle.'}]
            db.execute('INSERT INTO assignments VALUES(1,?,?,?,?,?,?,?)', ('Grammar check: ready, steady, go!', 'Времена, степени сравнения и пассивный залог. Небольшая практика в формате ОГЭ.', 15, 9, None, json.dumps(questions, ensure_ascii=False), time.time()))
            db.execute('INSERT INTO materials VALUES(1,?,?,?,?,?,?,?)', ('Present tenses: всё по полочкам', 'Когда использовать Simple, Continuous и Perfect. Сохрани, чтобы повторить перед практикой.', 'note', 'Present Simple — привычки и факты: I study every day.\nPresent Continuous — сейчас: I am studying now.\nPresent Perfect — опыт и результат: I have finished my homework.', 0, None, time.time()))
            db.execute('INSERT INTO materials VALUES(2,?,?,?,?,?,?,?)', ('Как готовиться к устной части', 'План короткой ежедневной тренировки: 5 минут чтения, 5 минут ответов и 5 минут монолога.', 'note', '1. Прочитай небольшой текст вслух.\n2. Запиши ответы на пять вопросов о себе.\n3. Прослушай запись и отметь одну вещь, которую улучшишь завтра.', 9, None, time.time()))
            (ROOT / 'data' / 'first-login.txt').write_text(f'Локальная первая настройка. Удалите этот файл после сохранения паролей.\nПреподаватель: polina / {teacher}\nДемоученик: alex / {student}\n', encoding='utf-8')
            print('Пароли первого входа: data/first-login.txt', flush=True)
        learning.migrate(db)
        academy.migrate(db)
        subjects.migrate(db)
        academy.seed(db)
        subjects.seed(db)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, data, cookie=None):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def user(self, db):
        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        token = cookie['studio'].value if 'studio' in cookie else ''
        return db.execute('SELECT u.id,u.name,u.login,u.role,u.grade,u.timezone FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()

    def do_GET(self):
        try:
            self.get()
        except (ValueError, KeyError):
            self.send(400, {'error': 'Некорректный запрос'})
        except Exception:
            self.send(500, {'error': 'Не получилось выполнить запрос'})

    def get(self):
        path = urlparse(self.path).path
        if path.startswith('/api/'):
            with connect() as db:
                user = self.user(db)
                if not user:
                    return self.send(401, {'error': 'Войдите в аккаунт'})
                if path == '/api/me':
                    return self.send(200, dict(user))
                if path == '/api/dashboard':
                    db.execute('BEGIN IMMEDIATE')
                    payload = learning.dashboard(db, user, self.allowed)
                    academy.sync(db)
                    academy.reminders(db, user, self.allowed)
                    payload['unread'] = db.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND seen=0',(user['id'],)).fetchone()[0]
                    db.commit()
                    return self.send(200, payload)
                return self.send(404, {'error': 'Не найдено'})
        if path.startswith('/uploads/'):
            with connect() as db:
                user = self.user(db)
                if not user:
                    return self.send(401, {'error': 'Войдите в аккаунт'})
                if not learning.file_allowed(db, user, path, self.allowed):
                    return self.send(403, {'error': 'Нет доступа'})
            filename = ROOT / 'uploads' / Path(path).name
        else:
            files = {'/': 'index.html', '/app.js': 'app.js', '/learning.js': 'learning.js', '/style.css': 'style.css', '/learning.css':'learning.css', '/academy.js':'academy.js', '/academy.css':'academy.css', '/icons.js':'icons.js', '/favicon.svg': 'logo.svg', '/logo.svg':'logo.svg', '/method.js':'method.js', '/method.css':'method.css'}
            if path not in files:
                return self.send(404, {'error': 'Не найдено'})
            filename = ROOT / 'web' / files[path]
        if not filename.is_file():
            return self.send(404, {'error': 'Файл не найден'})
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        size = filename.stat().st_size
        start, end, partial = 0, size-1, False
        range_header = self.headers.get('Range', '')
        if range_header.startswith('bytes='):
            try:
                left, right = range_header[6:].split('-')
                if left:
                    start = int(left); end = min(int(right), size-1) if right else size-1
                else:
                    start = max(0, size-int(right))
                if start < 0 or start > end or start >= size:
                    raise ValueError()
                partial = True
            except ValueError:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.end_headers(); return
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' https: blob:; frame-src https:; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if path.startswith('/uploads/'):
            self.send_header('Cache-Control', 'private, no-store')
        if partial:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        with filename.open('rb') as f:
            f.seek(start)
            remaining = end-start+1
            while remaining:
                chunk = f.read(min(65536, remaining))
                if not chunk: break
                self.wfile.write(chunk); remaining -= len(chunk)

    @staticmethod
    def allowed(item, user):
        return user['role'] == 'teacher' or ((item['student_id'] == user['id']) if item['student_id'] else item['grade'] in (0, user['grade']))

    def do_POST(self):
        try:
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.send(403, {'error': 'Недопустимый источник запроса'})
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):
                return self.send(403, {'error': 'Недопустимый источник запроса'})
            length = int(self.headers.get('Content-Length', 0))
            if length > 40*1024*1024:
                return self.send(413, {'error': 'Максимальный размер файла — 25 МБ. Для больших видео добавьте ссылку.'})
            if 'application/json' not in self.headers.get('Content-Type', ''):
                return self.send(415, {'error': 'Ожидается JSON'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError()
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self.post(db, body)
        except (ValueError, KeyError, TypeError):
            self.send(400, {'error': 'Проверьте заполнение полей'})
        except sqlite3.IntegrityError:
            self.send(409, {'error': 'Такой логин уже занят или запись уже существует'})
        except Exception:
            self.send(500, {'error': 'Не получилось сохранить. Попробуйте ещё раз.'})

    def post(self, db, b):
        path = urlparse(self.path).path
        if path == '/api/login':
            ip = self.client_address[0]
            limit = db.execute('SELECT * FROM login_limits WHERE ip=?', (ip,)).fetchone()
            if limit and limit['count'] >= 15 and limit['until'] > time.time():
                return self.send(429, {'error': 'Слишком много попыток. Подождите 15 минут.'})
            row = db.execute('SELECT * FROM users WHERE login=?', (str(b.get('login', '')).strip().lower(),)).fetchone()
            if not row or not password_ok(str(b.get('password', '')), row['password']):
                count = limit['count']+1 if limit and limit['until'] > time.time() else 1
                db.execute('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)', (ip, count, time.time()+900))
                return self.send(401, {'error': 'Неверный логин или пароль'})
            db.execute('DELETE FROM login_limits WHERE ip=?', (ip,))
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], time.time()+86400*7))
            return self.send(200, {'ok': True}, f'studio={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800' + ('; Secure' if COOKIE_SECURE else ''))
        u = self.user(db)
        if not u:
            return self.send(401, {'error': 'Войдите в аккаунт'})
        meta = academy.config_validate(db, b, learning) if path == '/api/assignments' or (path == '/api/edit-item' and b.get('entity') == 'assignment') else None
        subject_plan = subjects.prepare(db,path,b)
        handled = academy.dispatch(db, u, path, b, ROOT, self.allowed, learning)
        if handled is None:
            handled = learning.dispatch(db, u, path, b, ROOT, self.allowed)
        if handled is not None and handled[0] < 300 and meta:
            item_id = int(b['id']) if b.get('id') else db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('UPDATE assignments SET category=?,exam_config=? WHERE id=?',(meta[0],json.dumps(meta[1],ensure_ascii=False),item_id))
        if handled is not None:
            if handled[0]<300: subjects.save(db,subject_plan,b)
            db.commit()
            return self.send(*handled)
        if path == '/api/logout':
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            if 'studio' in cookie:
                db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(cookie['studio'].value.encode()).hexdigest(),))
            return self.send(200, {'ok': True}, 'studio=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
        if path == '/api/password':
            password = str(b['password'])
            row = db.execute('SELECT password FROM users WHERE id=?', (u['id'],)).fetchone()
            if len(password) < 10 or len(password)>200 or not password_ok(str(b.get('current', '')), row['password']):
                return self.send(400, {'error': 'Проверьте текущий пароль. Новый — от 10 до 200 символов.'})
            db.execute('UPDATE users SET password=? WHERE id=?', (password_hash(password), u['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (u['id'],))
            return self.send(200, {'ok': True}, 'studio=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
        if u['role'] != 'teacher':
            return self.send(403, {'error': 'Только для преподавателя'})
        if path == '/api/students':
            name = str(b['name']).strip()[:100]
            login = str(b['login']).strip().lower()
            grade = int(b['grade'])
            if not name or not login.isascii() or not login.replace('_', '').isalnum() or not 3 <= len(login) <= 40 or grade not in range(5,10): raise ValueError()
            password = secrets.token_urlsafe(10)
            db.execute('INSERT INTO users(name,login,password,role,grade) VALUES(?,?,?,?,?)', (name,login,password_hash(password),'student',grade))
            return self.send(201, {'login': login, 'password': password})
        if path == '/api/reset-password':
            row = db.execute("SELECT id FROM users WHERE id=? AND role='student'", (int(b['id']),)).fetchone()
            if not row: raise ValueError()
            password = secrets.token_urlsafe(10)
            db.execute('UPDATE users SET password=? WHERE id=?', (password_hash(password), row['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            return self.send(200, {'password': password})
        if path in ('/api/assignments', '/api/materials', '/api/lessons'):
            title = str(b['title']).strip()[:200]
            if not title: raise ValueError()
            student = int(b['student_id']) if b.get('student_id') else None
            if student and not db.execute("SELECT 1 FROM users WHERE id=? AND role='student'", (student,)).fetchone(): raise ValueError()
            grade = int(b.get('grade', 0))
            if grade not in (0,5,6,7,8,9): raise ValueError()
            if path == '/api/assignments':
                questions = b['questions']; minutes = int(b['minutes'])
                if not isinstance(questions,list) or not 1 <= len(questions) <= 60 or not 1 <= minutes <= 180: raise ValueError()
                clean = []
                for q in questions:
                    options = [str(x).strip()[:300] for x in q['options']]
                    if not q.get('prompt') or not 2 <= len(options) <= 6 or not all(options) or q['answer'] not in options or len(set(options))!=len(options): raise ValueError()
                    clean.append(dict(prompt=str(q['prompt'])[:2000], options=options, answer=str(q['answer']), explanation=str(q.get('explanation',''))[:2000]))
                db.execute('INSERT INTO assignments(title,description,minutes,grade,student_id,questions,created) VALUES(?,?,?,?,?,?,?)', (title,str(b.get('description',''))[:3000],minutes,grade,student,json.dumps(clean,ensure_ascii=False),time.time()))
            elif path == '/api/materials':
                kind = b['kind']; url = str(b.get('url','')).strip()
                if kind not in ('note','link','video','file'): raise ValueError()
                if kind in ('link','video') and urlparse(url).scheme != 'https': raise ValueError()
                if kind == 'file':
                    suffix = Path(str(b['filename'])).suffix.lower()
                    if suffix not in ('.pdf','.png','.jpg','.jpeg','.webp','.mp4','.webm','.mp3','.wav','.docx','.pptx'): raise ValueError()
                    raw = base64.b64decode(b['file'],validate=True)
                    if len(raw) > 25*1024*1024: return self.send(413, {'error':'Файл больше 25 МБ'})
                    name = secrets.token_hex(16)+suffix
                    (ROOT/'uploads'/name).write_bytes(raw); url='/uploads/'+name
                if not url: raise ValueError()
                db.execute('INSERT INTO materials(title,description,kind,url,grade,student_id,created) VALUES(?,?,?,?,?,?,?)', (title,str(b.get('description',''))[:3000],kind,url[:15000],grade,student,time.time()))
            else:
                from datetime import datetime
                datetime.fromisoformat(b['starts'])
                if not student or urlparse(b['url']).scheme != 'https' or not 10 <= int(b['minutes']) <= 180: raise ValueError()
                db.execute('INSERT INTO lessons(title,starts,minutes,student_id,url,notes) VALUES(?,?,?,?,?,?)', (title,b['starts'],int(b['minutes']),student,b['url'][:2000],str(b.get('notes',''))[:3000]))
            subjects.save(db,subject_plan,b)
            db.commit()
            return self.send(201, {'ok': True})
        self.send(404, {'error': 'Не найдено'})


class StudioServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    initialize()
    print(f'The Lesson Method: http://{args.host}:{args.port}', flush=True)
    StudioServer((args.host,args.port),Handler).serve_forever()
