"""Browser smoke test and responsive screenshots; temporary database only."""
import importlib.util
import json
import shutil
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('studio',root/'server.py')
studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
out=root/'docs'/'screenshots';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    studio.ROOT=Path(tmp);studio.DB=studio.ROOT/'data'/'ui.sqlite'
    shutil.copytree(root/'web',studio.ROOT/'web')
    studio.initialize()
    with studio.connect() as db:db.execute('UPDATE users SET password=?',(studio.password_hash('ui-password-123'),))
    server=studio.ThreadingHTTPServer(('127.0.0.1',0),studio.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url);page.locator('#login-form').wait_for()
            page.screenshot(path=str(out/'login-desktop.png'),full_page=True)
            page.locator('[name=login]').fill('alex');page.locator('[name=password]').fill('ui-password-123')
            page.get_by_role('button',name='Войти в кабинет').click()
            page.locator('.hero').wait_for()
            page.screenshot(path=str(out/'student-desktop.png'),full_page=True)
            for width,height,name in [(768,1024,'tablet'),(390,844,'mobile'),(360,800,'small-mobile')]:
                page.set_viewport_size({'width':width,'height':height})
                page.screenshot(path=str(out/f'student-{name}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Overflow at {width}'
            page.set_viewport_size({'width':1440,'height':1050})
            page.locator('article').filter(has=page.get_by_role('heading',name='Grammar check: ready, steady, go!')).locator('[data-action=start]').click()
            page.locator('[data-action=confirm-start]').click()
            page.locator('#quiz-form').wait_for()
            assert page.locator('#timer').inner_text()!='--:--'
            page.locator('[name=q0][value=goes]').check()
            page.reload()
            page.locator('.hero').wait_for()
            page.locator('article').filter(has=page.get_by_role('heading',name='Grammar check: ready, steady, go!')).locator('[data-action=start]').click()
            page.locator('#quiz-form').wait_for()
            assert page.locator('[name=q0][value=goes]').is_checked()
            page.locator('#quiz-form button[type=submit]').click()
            page.get_by_text('Ещё один шаг вперёд!',exact=True).wait_for()
            assert page.locator('.review').count()==6
            page.screenshot(path=str(out/'result.png'),full_page=True)
            page.locator('[data-page=tasks]').last.click()
            page.locator('[data-action=logout]').click()
            page.locator('#login-form').wait_for()
            page.locator('[name=login]').fill('polina');page.locator('[name=password]').fill('ui-password-123')
            page.get_by_role('button',name='Войти в кабинет').click()
            page.locator('.hero').wait_for()
            page.locator('[data-page=students]').click()
            page.locator('[data-action=new-student]').click()
            page.locator('#student-form [name=name]').fill('Мария')
            page.locator('#student-form [name=login]').fill('maria')
            page.locator('#student-form button[type=submit]').click()
            page.locator('.credential').wait_for()
            page.locator('[data-action=close]').click()
            assert page.get_by_role('cell',name='Мария',exact=True).count()==1
            page.screenshot(path=str(out/'teacher-desktop.png'),full_page=True)
            page.locator('[data-page=tasks]').click()
            page.locator('[data-action=new-task]').click()
            page.locator('#learning-task-form [name=title]').fill('New UI practice')
            page.locator('.q-prompt').fill('She ___ English.')
            page.locator('.q-options').fill('speak\nspeaks')
            page.locator('.q-answer').fill('speaks')
            page.locator('#learning-task-form button[type=submit]').click()
            page.get_by_role('heading',name='New UI practice').wait_for()
            page.locator('[data-page=materials]').click()
            page.locator('[data-action=new-material]').click()
            page.locator('#material-form [name=title]').fill('UI notes')
            page.locator('#material-form [name=url]').fill('Practice makes progress.')
            page.locator('#material-form button[type=submit]').click()
            page.get_by_role('heading',name='UI notes').wait_for()
            page.locator('[data-page=lessons]').click()
            page.locator('[data-action=new-lesson]').click()
            page.locator('#lesson-form [name=title]').fill('Speaking practice')
            page.locator('#lesson-form [name=starts]').fill('2026-11-05T16:00')
            page.locator('#lesson-form [name=url]').fill('https://meet.jit.si/studio-demo')
            page.locator('#lesson-form button[type=submit]').click()
            page.get_by_role('heading',name='Speaking practice').wait_for()
            assert not errors,errors
            browser.close()
            print(json.dumps({'result':'passed','viewports':[1440,768,390,360],'browser_errors':errors,'flows':['student login','quiz start','resume with selected answer','submit and review','teacher login','create student','create assignment','create material','schedule lesson']},ensure_ascii=True))
    finally:
        server.shutdown();server.server_close();thread.join()
