"""Local-only demonstration server. Python 3.11+, no third-party dependencies."""
import json, os, secrets, sqlite3, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
BASE=Path(__file__).resolve().parent
DB=BASE/'demo.sqlite3'
PASSWORD=os.environ.get('AEI_ADMIN_PASSWORD') or secrets.token_urlsafe(12)
TOKENS={}
LOCK=threading.Lock()
def db():
    c=sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS packages (revision INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, action TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    return c
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(BASE/'web'),**kw)
    def reply(self,status,data):
        body=json.dumps(data).encode(); self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if size>2000000: raise ValueError('Payload too large')
        return json.loads(self.rfile.read(size))
    def do_GET(self):
        if self.path=='/api/health': return self.reply(200,{'status':'ok','mode':'training'})
        if self.path=='/api/package':
            with db() as c: row=c.execute('SELECT revision,data FROM packages ORDER BY revision DESC LIMIT 1').fetchone()
            return self.reply(200,{'revision':row[0] if row else 0,'data':json.loads(row[1]) if row else None})
        return super().do_GET()
    def do_POST(self):
        if self.path!='/api/login': return self.reply(404,{'error':'Not found'})
        try: data=self.body()
        except (ValueError,TypeError): return self.reply(400,{'error':'Invalid JSON'})
        if not secrets.compare_digest(str(data.get('password','')),PASSWORD): return self.reply(401,{'error':'Invalid credentials'})
        token=secrets.token_urlsafe(32)
        with LOCK: TOKENS[token]=time.time()+3600
        return self.reply(200,{'token':token,'expires_in':3600})
    def do_PUT(self):
        if self.path!='/api/package': return self.reply(404,{'error':'Not found'})
        token=self.headers.get('Authorization','').removeprefix('Bearer ')
        with LOCK: expiry=TOKENS.get(token,0)
        if expiry<time.time(): return self.reply(401,{'error':'Login required'})
        try:
            data=self.body()
            if data.get('simulated') is not True or not all(isinstance(data.get(k),list) for k in ['roads','nodes','shelters','hazards','facilities','alerts']): raise ValueError('Invalid training package')
            for s in data['shelters']:
                if s['status'] not in ['OPEN','CLOSED','FULL'] or not 0<=s['available']<=s['capacity']: raise ValueError('Invalid shelter capacity/status')
            with db() as c:
                cursor=c.execute('INSERT INTO packages(data) VALUES (?)',(json.dumps(data),));rev=cursor.lastrowid
                c.execute('INSERT INTO audit(action) VALUES (?)',(f'Published training revision {rev}',))
            return self.reply(200,{'revision':rev})
        except (ValueError,KeyError,TypeError): return self.reply(400,{'error':'Invalid training package'})
if __name__=='__main__':
    db().close()
    print('AEI training demo: http://localhost:8080',flush=True)
    print('Local operations password: '+PASSWORD,flush=True)
    ThreadingHTTPServer((os.environ.get('AEI_BIND_HOST','127.0.0.1'),8080),Handler).serve_forever()
