"""Local-only demonstration server. Python 3.11+, no third-party dependencies."""
import json, os, secrets, sqlite3, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
BASE=Path(__file__).resolve().parent
DB=BASE/'demo.sqlite3'
PASSWORD=os.environ.get('AEI_ADMIN_PASSWORD') or secrets.token_urlsafe(12)
TOKENS={}
LOCK=threading.Lock()
class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def db():
    c=sqlite3.connect(DB,timeout=10,factory=ClosingConnection)
    c.execute('CREATE TABLE IF NOT EXISTS packages (revision INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, action TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    return c
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(BASE/'web'),**kw)
    def reply(self,status,data):
        body=json.dumps(data).encode(); self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=8000000: raise ValueError('Invalid payload size')
        value=json.loads(self.rfile.read(size))
        if not isinstance(value,dict): raise ValueError('JSON object required')
        return value
    def do_GET(self):
        if self.path=='/api/health': return self.reply(200,{'status':'ok','mode':'training'})
        if self.path=='/api/package':
            with db() as c: row=c.execute('SELECT revision,data FROM packages ORDER BY revision DESC LIMIT 1').fetchone()
            return self.reply(200,{'revision':row[0] if row else 0,'data':json.loads(row[1]) if row else None})
        return super().do_GET()
    def do_POST(self):
        if self.path in ['/api/check-in','/api/road-status','/api/training-alert']:
            return self.training_update()
        if self.path!='/api/login': return self.reply(404,{'error':'Not found'})
        try: data=self.body()
        except (ValueError,TypeError): return self.reply(400,{'error':'Invalid JSON'})
        if not secrets.compare_digest(str(data.get('password','')),PASSWORD): return self.reply(401,{'error':'Invalid credentials'})
        token=secrets.token_urlsafe(32)
        with LOCK: TOKENS[token]=time.time()+3600
        return self.reply(200,{'token':token,'expires_in':3600})
    def training_update(self):
        token=self.headers.get('Authorization','').removeprefix('Bearer ')
        with LOCK: expiry=TOKENS.get(token,0)
        if expiry<time.time(): return self.reply(401,{'error':'Login required'})
        try:
            payload=self.body()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute('SELECT data FROM packages ORDER BY revision DESC LIMIT 1').fetchone()
                if not row: return self.reply(409,{'error':'Publish a mobile area first'})
                data=json.loads(row[0])
                if data.get('networkSource')!='OpenStreetMap': return self.reply(409,{'error':'Publish a real-street mobile area first'})
                origin=payload.get('origin')
                if origin and any(abs(float(origin[k])-float(data['origin'][k]))>.0001 for k in ['lat','lon']):
                    return self.reply(409,{'error':'Training areas do not match'})
                if self.path=='/api/check-in':
                    delta=payload.get('count')
                    if isinstance(delta,bool) or not isinstance(delta,int) or delta==0: raise ValueError('Invalid check-in count')
                    shelter=next(x for x in data['shelters'] if x['id']==payload.get('shelter_id'))
                    if shelter['status']=='CLOSED': return self.reply(409,{'error':'Shelter is closed'})
                    if not 0<=shelter['available']-delta<=shelter['capacity']: return self.reply(409,{'error':'Capacity changed; refresh before retrying'})
                    shelter['available']-=delta
                    shelter['status']='FULL' if shelter['available']==0 else 'OPEN'
                    action=f"Check-in delta {delta} at {shelter['id']}"
                elif self.path=='/api/road-status':
                    if payload.get('status') not in ['OPEN','BLOCKED']: raise ValueError('Invalid road status')
                    road=next(x for x in data['roads'] if x['id']==payload.get('road_id'))
                    road['status']=payload['status'];action=f"Road {road['id']} {road['status']}"
                else:
                    message=payload.get('message')
                    if not isinstance(message,str) or not message.strip() or len(message)>500: raise ValueError('Invalid alert')
                    data['alerts']=(data['alerts']+[message.strip()])[-50:];action='Published foreground training alert'
                data['version']=int(data.get('version',3))+1
                data['updated']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                cursor=c.execute('INSERT INTO packages(data) VALUES (?)',(json.dumps(data),));revision=cursor.lastrowid
                c.execute('INSERT INTO audit(action) VALUES (?)',(action,))
            return self.reply(200,{'revision':revision,'data':data})
        except (ValueError,KeyError,TypeError,StopIteration): return self.reply(400,{'error':'Invalid training update'})
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
