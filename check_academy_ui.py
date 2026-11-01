"""Full browser checks for the eight new learning sections and the new theme."""
import importlib.util,json,shutil,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('studio',root/'server.py');studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
out=root/'docs'/'screenshots';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    studio.ROOT=Path(tmp);studio.DB=studio.ROOT/'data'/'ui.sqlite';shutil.copytree(root/'web',studio.ROOT/'web');studio.initialize()
    with studio.connect() as db:db.execute('UPDATE users SET password=?',(studio.password_hash('ui-password-123'),))
    server=studio.ThreadingHTTPServer(('127.0.0.1',0),studio.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
            tc=browser.new_context(viewport={'width':1440,'height':1050});sc=browser.new_context(viewport={'width':390,'height':844})
            teacher=tc.new_page();student=sc.new_page();errors=[]
            for pg in (teacher,student):pg.on('pageerror',lambda e:errors.append(str(e)));pg.on('dialog',lambda d:d.accept())
            def login(pg,who):
                pg.goto(url);pg.locator('#login-form').wait_for()
                assert pg.locator('.login-story').count()==0
                assert pg.locator('.login-form').count()==1
                pg.locator('[name=login]').fill(who);pg.locator('[name=password]').fill('ui-password-123');pg.get_by_role('button',name='Войти в кабинет').click();pg.locator('.hero').wait_for()
            def nav(pg,name):
                item=pg.locator(f'.nav [data-page={name}]')
                if item.is_visible():item.click()
                else:
                    pg.locator('[data-ac=menu]').click()
                    pg.locator(f'[data-ac=menu-go][data-route={name}]').click()
                pg.locator('#content .busy').wait_for(state='detached')
            teacher.goto(url);teacher.locator('#login-form').wait_for();teacher.screenshot(path=str(out/'login-blue-pink.png'),full_page=True)
            login(teacher,'polina');login(student,'alex')
            teacher.screenshot(path=str(out/'teacher-home-v3.png'),full_page=True)
            student.screenshot(path=str(out/'student-home-v3-mobile.png'),full_page=True)
            nav(student,'diagnostic')
            student.locator('article').filter(has=student.get_by_role('heading',name='Первый шаг: входная диагностика')).locator('[data-action=start]').click()
            student.locator('[data-action=confirm-start]').click();student.locator('#quiz-form').wait_for()
            student.locator('[name=q0][value=play]').check();student.locator('[name=q1]').fill('went');student.locator('[name=q2][value=cheap]').check();student.locator('[name=q3]').fill('library');student.locator('[name=q4][value="On foot"]').check();student.locator('[name=q5][value=Monday]').check()
            student.locator('.question-card').first.locator('[data-ac=thread]').click();student.locator('#comment-form [name=body]').fill('Почему здесь не play?');student.locator('#comment-form button[type=submit]').click();student.get_by_text('Почему здесь не play?',exact=True).wait_for();student.locator('[data-action=close]').click()
            student.locator('#quiz-form button[type=submit]').click();student.get_by_role('heading',name='Ещё один шаг вперёд!').wait_for()
            nav(student,'progress');expect(student.locator('.topic-grid')).to_contain_text('Времена');student.screenshot(path=str(out/'topic-progress-mobile.png'),full_page=True)
            nav(student,'mistakes');expect(student.locator('[data-ac=mistakes-start]')).to_be_visible();student.locator('[data-ac=mistakes-start]').click();student.locator('[data-action=confirm-start]').click();student.locator('#quiz-form').wait_for()
            student.locator('[data-learn=save-exit]').click();student.locator('#quiz-form').wait_for(state='detached')
            nav(student,'courses');student.get_by_role('heading',name='Времена без путаницы').wait_for();student.screenshot(path=str(out/'courses-mobile.png'),full_page=True)
            student.locator('article').filter(has=student.get_by_role('heading',name='Времена без путаницы')).locator('[data-ac=course-open]').click();student.locator('[data-ac=course-read]').first.click();expect(student.locator('.course-step').first).to_contain_text('Шаг завершён');student.locator('[data-action=close]').click()
            nav(student,'words');student.locator('[data-ac=word-new]').click();student.locator('#word-form [name=word]').fill('curious');student.locator('#word-form [name=translation]').fill('любознательный');student.locator('#word-form button[type=submit]').click();student.get_by_role('heading',name='curious',exact=True).wait_for()
            student.locator('[data-ac=word-drill]').click();student.locator('[data-ac=word-reveal]').click();student.locator('[data-ac=word-rate][data-known="1"]').click();student.locator('[data-action=close]').click();student.screenshot(path=str(out/'vocabulary-mobile.png'),full_page=True)
            nav(teacher,'courses');teacher.locator('[data-ac=course-new]').click();teacher.locator('#course-form [name=title]').fill('Reading club');teacher.locator('#course-form [name=step_title]').fill('Read a short story');teacher.locator('.step-body').fill('Start with the title. Then read for the main idea.');teacher.locator('#course-form button[type=submit]').click();teacher.get_by_role('heading',name='Reading club',exact=True).wait_for();teacher.screenshot(path=str(out/'courses-desktop.png'),full_page=True)
            nav(teacher,'discussions');teacher.locator('#threads [data-ac=thread]').first.click();expect(teacher.locator('.comment-thread')).to_contain_text('Почему здесь не play?');teacher.locator('#comment-form [name=body]').fill('После she добавляем -s. Получается plays.');teacher.locator('#comment-form button[type=submit]').click();teacher.get_by_text('После she добавляем -s. Получается plays.',exact=True).wait_for();teacher.screenshot(path=str(out/'private-discussion.png'),full_page=True);teacher.locator('[data-action=close]').click()
            nav(teacher,'mocks');teacher.locator('[data-ac=category-new]').click();teacher.locator('#learning-task-form [name=title]').fill('Two-section rehearsal');teacher.locator('[name=minutes]').fill('2');teacher.locator('[name=exam_sections]').fill('Reading | 1\nWriting | 1')
            q=teacher.locator('.question-editor').first;q.locator('.q-type').select_option('text');q.locator('.q-prompt').fill('Complete: I ___ English.');q.locator('.q-accepted').fill('like');q.locator('.q-topic').fill('Чтение');q.locator('.q-section').fill('Reading')
            teacher.locator('[data-action=add-question]').click();q=teacher.locator('.question-editor').last;q.locator('.q-type').select_option('essay');q.locator('.q-prompt').fill('Write a short email.');q.locator('.q-topic').fill('Письмо');q.locator('.q-section').fill('Writing');q.locator('.q-rubric').fill('Content | 3\nLanguage | 2');teacher.locator('#learning-task-form button[type=submit]').click();teacher.get_by_role('heading',name='Two-section rehearsal',exact=True).wait_for();teacher.screenshot(path=str(out/'mocks-desktop.png'),full_page=True)
            student.reload();student.locator('.hero').wait_for();nav(student,'mocks');student.locator('article').filter(has=student.get_by_role('heading',name='Two-section rehearsal')).locator('[data-action=start]').click();student.locator('[data-action=confirm-start]').click();student.locator('#quiz-form').wait_for();expect(student.locator('#section-status')).to_contain_text('Reading');expect(student.locator('[name=q1]')).to_be_disabled();student.locator('[name=q0]').fill('like');student.locator('[data-learn=save-exit]').click();student.locator('#quiz-form').wait_for(state='detached')
            nav(teacher,'calendar');teacher.screenshot(path=str(out/'calendar-desktop.png'),full_page=True)
            with teacher.expect_download() as download:teacher.locator('[data-ac=calendar-export]').click()
            assert download.value.suggested_filename=='polina-calendar.ics'
            nav(student,'notifications');expect(student.locator('#content')).to_contain_text('Ответ Полины');student.locator('[data-ac=notifications-read]').click()
            for width,height in [(360,800),(390,844),(768,1024),(1440,1050)]:
                student.set_viewport_size({'width':width,'height':height});nav(student,'courses');assert student.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            assert teacher.locator('svg.lucide').count()>10
            assert not errors,errors
            browser.close();print(json.dumps({'passed':True,'browser_errors':errors,'viewports':[360,390,768,1440],'features':['right-only login','blue/pink theme','provided Lucide icons','diagnostics','topic progress','mistake practice','courses and completion','course editor','vocabulary and scheduled repeat','private question discussions','mock editor with criteria','server-controlled section lock','calendar export','notifications']}))
    finally:server.shutdown();server.server_close();thread.join()
