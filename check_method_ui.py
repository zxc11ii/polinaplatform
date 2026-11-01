"""Validate The Lesson Method shell in both Python and GitHub Pages builds."""
import argparse,functools,importlib.util,json,shutil,tempfile,threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');args=parser.parse_args()
screens=root/'docs'/'screenshots';screens.mkdir(parents=True,exist_ok=True)
temp=tempfile.TemporaryDirectory()
if args.demo:
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root)))
    path='/_site/'
else:
    spec=importlib.util.spec_from_file_location('studio',root/'server.py');studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
    studio.ROOT=Path(temp.name);studio.DB=studio.ROOT/'data'/'test.sqlite';shutil.copytree(root/'web',studio.ROOT/'web');studio.initialize()
    with studio.connect() as db:db.execute('UPDATE users SET password=?',(studio.password_hash('method-test-123'),))
    server=ThreadingHTTPServer(('127.0.0.1',0),studio.Handler);path='/'
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1050});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}'+path)
        if not args.demo:
            page.locator('#login-form').wait_for();expect(page.locator('.login-story')).to_have_count(0)
            page.screenshot(path=str(screens/'tlm-login.png'),full_page=True)
            page.locator('[name=login]').fill('polina');page.locator('[name=password]').fill('method-test-123');page.locator('#login-form button[type=submit]').click()
        page.locator('.tlm-welcome').wait_for()
        expect(page.locator('.tlm-brand')).to_have_attribute('aria-label','The Lesson Method')
        expect(page.locator('.nav-label')).to_have_count(0);expect(page.locator('.top-actions .pill')).to_have_count(0)
        expect(page.locator('.tlm-date')).to_be_visible();expect(page.locator('.tlm-notification')).to_be_visible()
        text=page.locator('.sidebar .nav').inner_text()
        for label in ('Диагностика','Пробники','Материалы','Слова и карточки','Обсуждения','Уведомления'):assert label not in text,label
        for label in ('Банк заданий','Папка ошибок','Полезные файлы','Моё расписание','Мои результаты'):assert label in text,label
        assert page.locator('.tlm-subject-card').count()==3
        assert page.locator('.tlm-logo').first.evaluate('(img)=>img.complete&&img.naturalWidth>0')
        page.screenshot(path=str(screens/('tlm-demo-home.png' if args.demo else 'tlm-home-desktop.png')),full_page=True)
        page.locator('.tlm-parent[data-group=courses]').click()
        expect(page.locator('.tlm-parent[data-group=courses]')).to_have_attribute('aria-expanded','true')
        page.locator('#submenu-courses [data-subject=ru]').click();page.get_by_role('heading',name='Курсы · Русский',exact=True).wait_for()
        expect(page.locator('#content')).to_contain_text('Русский язык: пишем грамотно');expect(page.locator('#content')).not_to_contain_text('Времена без путаницы')
        page.locator('[data-ac=course-new]').click();expect(page.locator('#course-form [name=subject]')).to_have_value('ru')
        page.locator('#course-form [name=title]').fill('Русский: новый курс');page.locator('#course-form [name=step_title]').fill('Правила');page.locator('.step-body').fill('Короткое объяснение.');page.locator('#course-form button[type=submit]').click();page.get_by_role('heading',name='Русский: новый курс',exact=True).wait_for()
        page.screenshot(path=str(screens/'tlm-russian-courses.png'),full_page=True)
        page.locator('.tlm-parent[data-group=tasks]').click();page.locator('#submenu-tasks [data-subject=de]').click();page.get_by_role('heading',name='Банк заданий · Немецкий',exact=True).wait_for()
        expect(page.locator('#content')).to_contain_text('Deutsch: первые уверенные шаги');expect(page.locator('#content')).not_to_contain_text('Grammar check')
        page.locator('[data-action=new-task]').click();expect(page.locator('#learning-task-form [name=subject]')).to_have_value('de');page.locator('#learning-task-form [name=title]').fill('Deutsch: neue Aufgabe');page.locator('.q-prompt').fill('Ich ___ Anna.');page.locator('.q-options').fill('heiße\nheißt');page.locator('.q-answer').fill('heiße');page.locator('#learning-task-form button[type=submit]').click();page.get_by_role('heading',name='Deutsch: neue Aufgabe',exact=True).wait_for()
        page.locator('.nav [data-page=materials]').click();page.locator('#content .busy').wait_for(state='detached');page.locator('#content [data-tlm=subject][data-subject=ru]').click();page.get_by_role('heading',name='Полезные файлы',exact=True).wait_for();expect(page.locator('#content')).to_contain_text('Русский язык: пишем грамотно — памятка');expect(page.locator('#content')).not_to_contain_text('Present tenses')
        page.locator('.tlm-notification').click();page.get_by_role('heading',name='Уведомления',exact=True).wait_for()
        page.locator('.nav [data-page=home]').click()
        for width,height in [(1280,900),(768,1024),(390,844),(360,800)]:
            page.set_viewport_size({'width':width,'height':height});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
            if width==390:page.screenshot(path=str(screens/'tlm-home-mobile.png'),full_page=True)
        page.locator('.tlm-parent[data-group=courses]').click();page.locator('#modal [data-subject=en]').click();page.get_by_role('heading',name='Курсы · Английский',exact=True).wait_for()
        page.locator('[data-tlm=menu]').click();expect(page.locator('#modal')).not_to_contain_text('Диагностика');expect(page.locator('#modal')).not_to_contain_text('Пробники');page.locator('#modal [data-route=progress]').click();page.get_by_role('heading',name='Мои результаты',exact=True).wait_for()
        assert not errors,errors
        browser.close();print(json.dumps(dict(result='passed',mode='pages' if args.demo else 'python',viewports=[1440,1280,768,390,360],checks=['TLM logo and name','exact sidebar labels','animated subject expansion','Russian course creation','German assignment creation','subject-specific useful files','header notification bell and date','mobile subject chooser','responsive layout']),ensure_ascii=True))
finally:server.shutdown();server.server_close();thread.join();temp.cleanup()
