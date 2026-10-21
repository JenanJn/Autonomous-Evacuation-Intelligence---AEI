/** Local risk-aware routing. scenario() is retained only for legacy synthetic tests. */
(function(root){
function scenario(lat=13.0827,lon=80.2707,type='Flood') {
 const c=Math.max(.1,Math.cos(lat*Math.PI/180)), nodes=[];
 for(let y=-2;y<=2;y++)for(let x=-2;x<=2;x++)nodes.push({id:`${x},${y}`,lat:lat+y*.0036,lon:lon+x*.0036/c});
 const roads=[];
 for(const n of nodes){const [x,y]=n.id.split(',').map(Number);for(const [dx,dy] of [[1,0],[0,1]]){let v=`${x+dx},${y+dy}`;if(nodes.some(a=>a.id===v)) roads.push({id:`R${roads.length+1}`,u:n.id,v,distance:400,status:'OPEN',risk:x===0&&y===1?.9:.05,accessible:true});}}
 const shelters=[['S1','Civic relief centre','2,0',200],['S2','Community safe haven','-2,-1',250],['S3','District evacuation hall','1,-2',180]].map(([id,name,node,capacity])=>({...nodes.find(n=>n.id===node),id,name,node,capacity,available:capacity-20,status:'OPEN',medical:true,food:true,water:true,toilets:true,accessible:true,address:'Simulated facility near your demo location',contact:'Demo desk — no real telephone'}));
 return {version:1,updated:new Date().toISOString(),simulated:true,origin:{lat,lon},nodes,roads,shelters,hazards:[{id:'H1',type,severity:'HIGH',lat:lat+.004,lon:lon+.0018/c,radius:330,active:true}],facilities:[{name:'Demo medical station',lat:lat-.0036,lon:lon-.0036/c,type:'Hospital'}],alerts:[]};
}
function metres(a,b){const r=Math.PI/180,dl=(b.lat-a.lat)*r,dn=(b.lon-a.lon)*r;return 6371000*2*Math.asin(Math.min(1,Math.sqrt(Math.sin(dl/2)**2+Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin(dn/2)**2)));}
function inside(p,polygon){if(!polygon||polygon.length<3)return false;let yes=false;for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){const a=polygon[i],b=polygon[j];if((a.lat>p.lat)!==(b.lat>p.lat)&&p.lon<(b.lon-a.lon)*(p.lat-a.lat)/(b.lat-a.lat)+a.lon)yes=!yes;}return yes;}
function intersects(a,b,h){
 if(h.shape?.length){if(inside(a,h.shape)||inside(b,h.shape))return true;const cross=(p,q,r)=>(q.lon-p.lon)*(r.lat-p.lat)-(q.lat-p.lat)*(r.lon-p.lon);for(let i=1;i<=h.shape.length;i++){const c=h.shape[i-1],d=h.shape[i%h.shape.length],v=[cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)];if(v[0]*v[1]<=0&&v[2]*v[3]<=0&&Math.max(Math.min(a.lon,b.lon),Math.min(c.lon,d.lon))<=Math.min(Math.max(a.lon,b.lon),Math.max(c.lon,d.lon))&&Math.max(Math.min(a.lat,b.lat),Math.min(c.lat,d.lat))<=Math.min(Math.max(a.lat,b.lat),Math.max(c.lat,d.lat)))return true;}return false;}
 const c=Math.cos(h.lat*Math.PI/180),ax=(a.lon-h.lon)*111320*c,ay=(a.lat-h.lat)*111320,bx=(b.lon-h.lon)*111320*c,by=(b.lat-h.lat)*111320;const t=Math.max(0,Math.min(1,-(ax*(bx-ax)+ay*(by-ay))/((bx-ax)**2+(by-ay)**2||1)));return Math.hypot(ax+t*(bx-ax),ay+t*(by-ay))<=h.radius;
}
function project(p,a,b){const c=Math.max(.05,Math.cos(p.lat*Math.PI/180)),x=(b.lon-a.lon)*c,y=b.lat-a.lat,t=Math.max(0,Math.min(1,((p.lon-a.lon)*c*x+(p.lat-a.lat)*y)/(x*x+y*y||1)));return {point:{lat:a.lat+t*(b.lat-a.lat),lon:a.lon+t*(b.lon-a.lon)},t};}
function allowed(r,accessible,mode){return r.status==='OPEN'&&(!accessible||r.accessible)&&(mode==='walking'?r.walking!==false:r.driving!==false);}
class Heap{constructor(){this.a=[];}push(item){const a=this.a;let i=a.length;a.push(item);while(i){const p=(i-1)>>1;if(a[p][0]<=item[0])break;a[i]=a[p];i=p;}a[i]=item;}pop(){const a=this.a,first=a[0],last=a.pop();if(a.length){let i=0;while(i*2+1<a.length){let c=i*2+1;if(c+1<a.length&&a[c+1][0]<a[c][0])c++;if(a[c][0]>=last[0])break;a[i]=a[c];i=c;}a[i]=last;}return first;}get size(){return this.a.length;}}
function route(s,position,dest,accessible=false,mode='walking'){
 if(!s.nodes.length||!s.nodes.some(n=>n.id===dest)||s.hazards.some(h=>h.active&&(h.shape?inside(position,h.shape):metres(position,h)<h.radius)))return null;
 const nodes=new Map(s.nodes.map(n=>[n.id,n])),adj=new Map(),byId=new Map();
 let snap=null;
 for(const road of s.roads){const a=nodes.get(road.u),b=nodes.get(road.v);if(!a||!b||!allowed({...road,status:'OPEN'},accessible,mode))continue;
  // Snap to the physically nearest accessible road before testing hazard closures.
  // Never teleport past a blocked section onto a farther road.
  const projection=project(position,a,b),d=metres(position,projection.point);
  if(!snap||d<snap.distance)snap={road,...projection,distance:d};
 }
 if(!snap||snap.distance>350||s.hazards.some(h=>h.active&&intersects(position,snap.point,h)))return null;
 const risk=r=>{const a=nodes.get(r.u),b=nodes.get(r.v),mid={lat:(a.lat+b.lat)/2,lon:(a.lon+b.lon)/2};return Math.max(0,r.risk||0)+s.hazards.reduce((sum,h)=>sum+(h.active&&metres(mid,h)<h.radius*2.2?({LOW:.1,MODERATE:.2,HIGH:.4,CRITICAL:.7}[h.severity]||.2):0),0);},speed=r=>mode==='walking'?75:Math.max(8,Math.min(mode==='ambulance'?50:40,r.speedKph||25))*1000/60;
 const cost=(r,d)=>d/speed(r)*(1+risk(r)*8);
 for(const r of s.roads){const a=nodes.get(r.u),b=nodes.get(r.v);if(!a||!b||!allowed(r,accessible,mode)||s.hazards.some(h=>h.active&&intersects(a,b,h)))continue;byId.set(r.id,r);if(!adj.has(r.u))adj.set(r.u,[]);if(!adj.has(r.v))adj.set(r.v,[]);if(mode==='walking'||r.oneway!==-1)adj.get(r.u).push({v:r.v,r});if(mode==='walking'||r.oneway!==1)adj.get(r.v).push({v:r.u,r});}
 const nearNode=s.nodes.reduce((a,b)=>metres(a,position)<metres(b,position)?a:b);
 const atIntersection=metres(nearNode,position)<=12;
 if(!atIntersection&&!byId.has(snap.road.id))return null;
 const dist=new Map(),prev=new Map(),heap=new Heap();const r=snap.road;
 const seed=(id,length)=>{const value=cost(r,length);if(value<(dist.get(id)??Infinity)){dist.set(id,value);prev.set(id,{root:true,edge:r.id,length});heap.push([value,id]);}};
 if(atIntersection){dist.set(nearNode.id,0);prev.set(nearNode.id,{root:true,length:0});heap.push([0,nearNode.id]);snap.point=nearNode;}
 else {if(mode==='walking'||r.oneway!==1)seed(r.u,r.distance*snap.t);if(mode==='walking'||r.oneway!==-1)seed(r.v,r.distance*(1-snap.t));}
 while(heap.size){const [value,u]=heap.pop();if(value!==dist.get(u))continue;if(u===dest)break;for(const item of adj.get(u)||[]){const next=value+cost(item.r,item.r.distance);if(next<(dist.get(item.v)??Infinity)){dist.set(item.v,next);prev.set(item.v,{u,edge:item.r.id,length:item.r.distance});heap.push([next,item.v]);}}}
 if(!Number.isFinite(dist.get(dest)))return null;
 const path=[dest],edges=[],lengths=[];let cursor=dest;
 while(prev.has(cursor)){const step=prev.get(cursor);if(step.edge){edges.unshift(step.edge);lengths.unshift(step.length);}if(step.root)break;cursor=step.u;path.unshift(cursor);}
 const geometry=[snap.point,...path.map(id=>nodes.get(id))].filter((p,i,a)=>!i||metres(p,a[i-1])>.2);
 const distance=lengths.reduce((a,b)=>a+b,0),minutes=Math.max(1,Math.ceil(lengths.reduce((a,d,i)=>a+d/speed(byId.get(edges[i])),0)));
 return {path,edges,geometry,legDistances:lengths,distance,cost:dist.get(dest),minutes,snapDistance:snap.distance,mode};
}
function options(s,p,accessible=false,mode='walking'){return s.shelters.filter(a=>a.status==='OPEN'&&a.available>0&&(!accessible||a.accessible)&&!s.hazards.some(h=>h.active&&(h.shape?inside(a,h.shape):metres(a,h)<h.radius))).map(a=>({shelter:a,route:route(s,p,a.node,accessible,mode)})).filter(a=>a.route).sort((a,b)=>a.route.cost-b.route.cost);}
function bearing(a,b){const rad=Math.PI/180,dl=(b.lon-a.lon)*rad;return (Math.atan2(Math.sin(dl)*Math.cos(b.lat*rad),Math.cos(a.lat*rad)*Math.sin(b.lat*rad)-Math.sin(a.lat*rad)*Math.cos(b.lat*rad)*Math.cos(dl))*180/Math.PI+360)%360;}
function guidance(area,route){if(!route)return {symbol:'↑',instruction:'Choose a reachable shelter',next:'Preview the route before navigating.'};const points=route.geometry||route.path.map(id=>area.nodes.find(n=>n.id===id));const segments=[];for(let i=1;i<points.length;i++){const d=metres(points[i-1],points[i]);if(d>1)segments.push({distance:d,bearing:bearing(points[i-1],points[i]),name:area.roads.find(r=>r.id===route.edges[Math.min(i-1,route.edges.length-1)])?.name});}if(!segments.length)return {symbol:'✓',instruction:'Shelter is ahead',next:'Check the destination and your surroundings.'};let distance=segments[0].distance,next='Continue toward your destination.';for(let i=1;i<segments.length;i++){const turn=((segments[i].bearing-segments[i-1].bearing+540)%360)-180;if(Math.abs(turn)>28){next=Math.abs(turn)>155?'Then make a U-turn':turn>0?'Then turn right':'Then turn left';break;}distance+=segments[i].distance;}const direction=['north','northeast','east','southeast','south','southwest','west','northwest'][Math.round(segments[0].bearing/45)%8];return {symbol:'↑',instruction:`Head ${direction} for ${Math.max(5,Math.round(distance/5)*5)} m`,next:segments[0].name?`${next} · ${segments[0].name}`:next};}
const api={scenario,metres,intersects,inside,project,route,options,bearing,guidance};if(typeof module!=='undefined')module.exports=api;root.Engine=api;
})(globalThis);
