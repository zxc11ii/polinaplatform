"""Old public demo storage upgrades without losing edits or duplicating subjects."""
import functools,json,threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent.parent/'_site'
seed=json.loads((root/'demo-seed.js').read_text(encoding='utf-8').split('=',1)[1].strip().removesuffix(';'))
seed['version']=1;seed.pop('tlmSubjectsV1',None)
for table in ('assignments','materials','courses','lessons'):
    seed[table]=[r for r in seed[table] if r.get('subject','en')=='en']
    for row in seed[table]:row.pop('subject',None)
seed['courses'].append(dict(id=1000,title='Курс, созданный Полиной раньше',description='Сохранить при обновлении',steps='[]',grade=0,student_id=None,archived=0,revision=1,created=1))
seed['vocabulary'].append(dict(id=1000,user_id=2,word='preserved',translation='сохранённый',example='',audio='',next_due=0,stage=0,archived=0,revision=1))
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root.parent)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
        page=browser.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/_site/')
        page.locator('.tlm-welcome').wait_for()
        page.evaluate('(state)=>localStorage.setItem("polina-interactive-demo-v1",JSON.stringify(state))',seed);page.reload();page.locator('.tlm-welcome').wait_for()
        actual=page.evaluate('JSON.parse(localStorage.getItem("polina-interactive-demo-v1"))')
        assert actual['version']==2
        assert any(c['id']==1000 and c['title']=='Курс, созданный Полиной раньше' for c in actual['courses'])
        assert any(w['word']=='preserved' for w in actual['vocabulary'])
        count=len(actual['courses']);assert {'ru','en','de'}=={c['subject'] for c in actual['courses']}
        page.reload();page.locator('.tlm-welcome').wait_for()
        assert page.evaluate('JSON.parse(localStorage.getItem("polina-interactive-demo-v1")).courses.length')==count
        browser.close();print('Old demo storage upgrade OK: previous courses and words preserved; subjects added once.')
finally:server.shutdown();server.server_close();thread.join()
