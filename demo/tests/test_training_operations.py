import importlib.util, pathlib, tempfile, threading, json, urllib.request, urllib.error, unittest
from concurrent.futures import ThreadPoolExecutor
ROOT=pathlib.Path(__file__).resolve().parents[2]
# When installed under demo/tests, the project root is two levels above this file.
SERVER=ROOT/'demo/server.py'
spec=importlib.util.spec_from_file_location('training_server',SERVER);server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
class Operations(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();server.DB=pathlib.Path(cls.tmp.name)/'test.sqlite3';server.TOKENS['test-token']=10**12
  cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.http.server_port)
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
 def request(self,path,body=None,token='test-token',method='POST'):
  req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method=method)
  try:
   with urllib.request.urlopen(req,timeout=10) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def seed(self):
  area={'networkSource':'OpenStreetMap','simulated':True,'version':3,'origin':{'lat':1,'lon':2},'nodes':[],'roads':[{'id':'W1','status':'OPEN'}],'shelters':[{'id':'S1','name':'Test shelter','capacity':20,'available':20,'status':'OPEN'}],'hazards':[],'facilities':[],'alerts':[]}
  self.assertEqual(self.request('/api/package',area,method='PUT')[0],200)
 def test_atomic_capacity_and_updates(self):
  self.seed();self.assertEqual(self.request('/api/check-in',{'shelter_id':'S1','count':1},token='wrong')[0],401)
  with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.request('/api/check-in',{'shelter_id':'S1','count':2}),range(12)))
  self.assertEqual(sum(status==200 for status,_ in results),10)
  _,package=self.request('/api/package',method='GET');shelter=package['data']['shelters'][0];self.assertEqual(shelter['available'],0);self.assertEqual(shelter['status'],'FULL')
  code,body=self.request('/api/check-in',{'shelter_id':'S1','count':-5});self.assertEqual(code,200);self.assertEqual(body['data']['shelters'][0]['status'],'OPEN')
  self.assertEqual(self.request('/api/check-in',{'shelter_id':'S1','count':True})[0],400)
  self.assertEqual(self.request('/api/check-in',{'shelter_id':'S1','count':1,'origin':{'lat':40,'lon':20}})[0],409)
  code,body=self.request('/api/road-status',{'road_id':'W1','status':'BLOCKED'});self.assertEqual(code,200);self.assertEqual(body['data']['roads'][0]['status'],'BLOCKED')
  code,body=self.request('/api/training-alert',{'message':'Training warning'});self.assertEqual(code,200);self.assertEqual(body['data']['alerts'][-1],'Training warning')
  with server.db() as c:self.assertGreater(c.execute('SELECT COUNT(*) FROM audit').fetchone()[0],10)
if __name__=='__main__':unittest.main()
