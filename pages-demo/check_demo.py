"""End-to-end check of the static, interactive GitHub Pages build."""
import functools,threading,sys
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
root=Path(sys.argv[1] if len(sys.argv)>1 else '_site').resolve()
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root.parent)))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1050},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}/{root.name}/');page.locator('.hero').wait_for()
        expect(page.locator('#demo-bar')).to_contain_text('Изменения только в этом браузере')
        expect(page.locator('h1')).to_contain_text('Полина')
        def nav(name):
            item=page.locator(f'.nav [data-page={name}]')
            if item.is_visible():item.click()
            else:page.locator('[data-ac=menu]').click();page.locator(f'[data-ac=menu-go][data-route={name}]').click()
            page.locator('#content .busy').wait_for(state='detached')
        nav('courses');page.locator('[data-ac=course-new]').click();page.locator('#course-form [name=title]').fill('Курс для проверки');page.locator('#course-form [name=step_title]').fill('Первое объяснение');page.locator('.step-body').fill('This is a new lesson.');page.locator('#course-form button[type=submit]').click();page.get_by_role('heading',name='Курс для проверки',exact=True).wait_for()
        nav('tasks');page.locator('[data-action=new-task]').click();page.locator('#learning-task-form [name=title]').fill('Проверка на GitHub');page.locator('.q-prompt').fill('She ___ English.');page.locator('.q-options').fill('speak\nspeaks');page.locator('.q-answer').fill('speaks');page.locator('#learning-task-form button[type=submit]').click();page.get_by_role('heading',name='Проверка на GitHub',exact=True).wait_for()
        nav('students');row=page.locator('tr').filter(has_text='Личное письмо: любимый предмет');row.locator('[data-learn=attempt]').click();page.locator('[name=rubric0_0]').fill('3');page.locator('[name=rubric0_1]').fill('2');page.locator('#review-form [name=feedback]').fill('Отличное письмо!');page.locator('#review-form button[type=submit]').click();expect(page.locator('tr').filter(has_text='Личное письмо: любимый предмет')).to_contain_text('5 / 5')
        page.locator('[data-demo-role=student]').click();page.locator('.hero').wait_for();expect(page.locator('h1')).to_contain_text('Александра')
        nav('courses');page.locator('article').filter(has=page.get_by_role('heading',name='Курс для проверки',exact=True)).locator('[data-ac=course-open]').click();page.locator('[data-ac=course-read]').click();expect(page.locator('.course-step')).to_contain_text('Шаг завершён');page.locator('[data-action=close]').click()
        nav('tasks');page.locator('article').filter(has=page.get_by_role('heading',name='Проверка на GitHub',exact=True)).locator('[data-action=start]').click();page.locator('[data-action=confirm-start]').click();page.locator('[name=q0][value=speaks]').check();page.locator('#quiz-form button[type=submit]').click();page.get_by_role('heading',name='Ещё один шаг вперёд!').wait_for();expect(page.locator('#content')).to_contain_text('1 из 1')
        nav('words');page.locator('[data-ac=word-new]').click();page.locator('#word-form [name=word]').fill('sunshine');page.locator('#word-form [name=translation]').fill('солнечный свет');page.locator('#word-form button[type=submit]').click();page.get_by_role('heading',name='sunshine',exact=True).wait_for();page.reload();page.locator('.hero').wait_for();nav('words');page.get_by_role('heading',name='sunshine',exact=True).wait_for();page.locator('[data-ac=word-drill]').click();page.locator('[data-ac=word-reveal]').click();page.locator('[data-ac=word-rate][data-known="1"]').click();page.locator('[data-action=close]').click()
        nav('mistakes');page.locator('[data-ac=mistakes-start]').click();page.locator('[data-action=confirm-start]').click();page.locator('#quiz-form').wait_for();page.locator('[data-learn=save-exit]').click();page.locator('#quiz-form').wait_for(state='detached')
        nav('calendar')
        with page.expect_download() as download:page.locator('[data-ac=calendar-export]').click()
        assert download.value.suggested_filename=='polina-calendar.ics'
        for name in ['progress','diagnostic','mocks','notifications','discussions','materials','account']:
            nav(name)
        page.set_viewport_size({'width':390,'height':844});nav('courses');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        browser.close();print('Interactive Pages demo OK: role switch, course editing/completion, assignment creation/solution, manual criteria review, persistent vocabulary, mistakes, calendar and mobile navigation.')
finally:server.shutdown();server.server_close();thread.join()
