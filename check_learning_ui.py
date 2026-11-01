"""End-to-end teacher/student flows with fake microphone and disposable database."""
import importlib.util
import io
import json
import shutil
import tempfile
import threading
import wave
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('studio',root/'server.py')
studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
out=root/'docs'/'screenshots';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    studio.ROOT=Path(tmp);studio.DB=studio.ROOT/'data'/'learning-ui.sqlite'
    shutil.copytree(root/'web',studio.ROOT/'web');studio.initialize()
    with studio.connect() as db:db.execute('UPDATE users SET password=?',(studio.password_hash('ui-password-123'),))
    server=studio.ThreadingHTTPServer(('127.0.0.1',0),studio.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'])
            teacher_context=browser.new_context(viewport={'width':1440,'height':1050})
            student_context=browser.new_context(viewport={'width':390,'height':844},permissions=['microphone'])
            teacher=teacher_context.new_page();student=student_context.new_page();errors=[]
            for page in (teacher,student):
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('dialog',lambda d:d.accept())
            def login(page,user):
                page.goto(url);page.locator('#login-form').wait_for()
                page.locator('[name=login]').fill(user);page.locator('[name=password]').fill('ui-password-123')
                page.get_by_role('button',name='Войти в кабинет').click();page.locator('.hero').wait_for()
            login(teacher,'polina');login(student,'alex')
            teacher.locator('[data-page=account]').click()
            teacher.locator('#timezone-form [name=timezone]').select_option('Europe/Moscow')
            teacher.locator('#timezone-form button').click()
            teacher.wait_for_function("() => data.user.timezone==='Europe/Moscow'")
            expect(teacher.locator('#timezone-form [name=timezone]')).to_have_value('Europe/Moscow')
            assert teacher.evaluate("localToUTC('2026-11-07T16:00')")=='2026-11-07T13:00:00.000Z'
            teacher.locator('[data-page=tasks]').first.click();teacher.locator('[data-action=new-task]').click()
            teacher.locator('#learning-task-form [name=title]').fill('Skills laboratory')
            teacher.locator('#learning-task-form [name=due]').fill('2099-11-08T16:00')
            editor=teacher.locator('.question-editor').nth(0)
            editor.locator('.q-prompt').fill('Listen. She ___ English.')
            editor.locator('.q-options').fill('speak\nspeaks');editor.locator('.q-answer').fill('speaks')
            wav=io.BytesIO()
            with wave.open(wav,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*8000)
            editor.locator('.q-audio-file').set_input_files({'name':'listening.wav','mimeType':'audio/wav','buffer':wav.getvalue()})
            for kind,prompt in [('text','Write the past of go'),('essay','Write an email to a friend'),('voice','Tell me about your school')]:
                teacher.locator('[data-action=add-question]').click();q=teacher.locator('.question-editor').last
                q.locator('.q-type').select_option(kind);q.locator('.q-prompt').fill(prompt)
                if kind=='text':q.locator('.q-accepted').fill('went')
            teacher.screenshot(path=str(out/'editor-mixed.png'),full_page=True)
            teacher.locator('#learning-task-form button[type=submit]').click()
            teacher.get_by_role('heading',name='Skills laboratory').wait_for()
            teacher.screenshot(path=str(out/'tasks-v2.png'),full_page=True)
            student.reload();student.locator('.hero').wait_for();student.locator('[data-page=tasks]').first.click()
            card=student.locator('article').filter(has=student.get_by_role('heading',name='Skills laboratory'))
            card.locator('[data-action=start]').click();student.locator('[data-action=confirm-start]').click();student.locator('#quiz-form').wait_for()
            expect(student.locator('audio')).to_have_count(1)
            student.locator('[name=q0][value=speaks]').check();student.locator('[name=q1]').fill('went')
            student.locator('[name=q2]').fill('Dear Sam, I really enjoy learning English with Polina. See you soon!')
            student.wait_for_function("() => document.querySelector('#save-status').textContent.startsWith('Сохранено на сервере')")
            # New browser storage / new login proves draft does not depend on sessionStorage.
            second_context=browser.new_context(viewport={'width':768,'height':1024})
            second=second_context.new_page();login(second,'alex');second.locator('[data-page=tasks]').first.click()
            second.locator('article').filter(has=second.get_by_role('heading',name='Skills laboratory')).locator('[data-action=start]').click()
            expect(second.locator('[name=q2]')).to_have_value('Dear Sam, I really enjoy learning English with Polina. See you soon!')
            second_context.close()
            student.locator('[data-learn=record]').click()
            expect(student.locator('[data-learn=record]')).to_have_text('Остановить запись')
            student.wait_for_timeout(1200)  # Let the fake audio source produce an actual recording.
            student.locator('[data-learn=record]').click()
            expect(student.locator('#voice-status-3')).to_have_text('Аудио сохранено на сервере')
            expect(student.locator('audio')).to_have_count(2)
            student.locator('audio').last.evaluate('(el) => el.play()')
            student.wait_for_function("() => document.querySelectorAll('audio')[1].currentTime > 0")
            student.locator('audio').last.evaluate('(el) => el.pause()')
            student.screenshot(path=str(out/'mixed-task-mobile.png'),full_page=True)
            student.set_viewport_size({'width':1440,'height':1050})
            student.screenshot(path=str(out/'mixed-task-desktop.png'),full_page=True)
            student.locator('#quiz-form button[type=submit]').click()
            student.get_by_role('heading',name='Работа отправлена Полине').wait_for()
            teacher.locator('[data-page=home]').click();teacher.reload();teacher.locator('.hero').wait_for()
            teacher.locator('[data-page=students]').click()
            row=teacher.locator('tr').filter(has_text='Skills laboratory')
            row.locator('[data-learn=attempt]').click();teacher.locator('#review-form').wait_for()
            teacher.locator('[name=mark2]').fill('4');teacher.locator('[name=mark3]').fill('5')
            teacher.locator('[name=feedback]').fill('Great email. Keep practising your pronunciation!')
            teacher.screenshot(path=str(out/'manual-review.png'),full_page=True)
            teacher.locator('#review-form button[type=submit]').click()
            teacher.locator('tr').filter(has_text='Skills laboratory').locator('[data-learn=retry]').click()
            teacher.locator('[data-learn=confirm-retry]').click()
            student.locator('[data-page=tasks]').last.click();student.reload();student.locator('.hero').wait_for()
            student.locator('[data-page=tasks]').first.click()
            card=student.locator('article').filter(has=student.get_by_role('heading',name='Skills laboratory'))
            expect(card).to_contain_text('Разрешена ещё попытка')
            card.locator('[data-learn=attempt]').click()
            expect(student.locator('#content')).to_contain_text('Great email. Keep practising your pronunciation!')
            student.locator('[data-page=tasks]').last.click()
            teacher.locator('[data-page=tasks]').first.click()
            card=teacher.locator('article').filter(has=teacher.get_by_role('heading',name='Skills laboratory'))
            card.locator('[data-learn=edit-task]').click()
            teacher.locator('#learning-task-form [name=title]').fill('Skills laboratory revised')
            teacher.locator('#learning-task-form button[type=submit]').click()
            card=teacher.locator('article').filter(has=teacher.get_by_role('heading',name='Skills laboratory revised'))
            card.locator('[data-learn=archive-task]').click();teacher.locator('[data-learn=confirm-archive]').click()
            expect(teacher.get_by_role('heading',name='Skills laboratory revised')).to_have_count(0)
            teacher.locator('[data-learn=task-tab][data-value=archive]').click()
            teacher.get_by_role('heading',name='Skills laboratory revised').wait_for()
            teacher.screenshot(path=str(out/'archive.png'),full_page=True)
            teacher.locator('[data-page=materials]').click()
            teacher.locator('[data-learn=edit-material]').first.click()
            teacher.locator('#learning-material-form [name=title]').fill('Edited useful material')
            teacher.locator('#learning-material-form button[type=submit]').click()
            teacher.get_by_role('heading',name='Edited useful material').wait_for()
            for width in (360,390,768,1440):
                student.set_viewport_size({'width':width,'height':900})
                assert student.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Overflow at {width}'
            assert not errors,errors
            browser.close()
            print(json.dumps({'passed':True,'flows':['timezone UTC conversion','mixed assignment editor','listening audio','server draft on fresh browser','microphone recording','voice upload','manual review','teacher feedback','retake permission','edit assignment','archive assignment','edit material'],'browser_errors':errors}))
    finally:
        server.shutdown();server.server_close();thread.join()
