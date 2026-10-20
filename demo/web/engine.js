/** Pure, deterministic local evacuation engine. All infrastructure is simulated. */
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
function intersects(a,b,h){const c=Math.cos(h.lat*Math.PI/180), ax=(a.lon-h.lon)*111320*c,ay=(a.lat-h.lat)*111320,bx=(b.lon-h.lon)*111320*c,by=(b.lat-h.lat)*111320;let t=Math.max(0,Math.min(1,-(ax*(bx-ax)+ay*(by-ay))/((bx-ax)**2+(by-ay)**2||1)));return Math.hypot(ax+t*(bx-ax),ay+t*(by-ay))<=h.radius;}
function route(s,position,dest,accessible=false){
 const origin=s.nodes.reduce((a,b)=>metres(position,a)<metres(position,b)?a:b), dist={[origin.id]:0},prev={},pending=new Set(s.nodes.map(n=>n.id));
 while(pending.size){let u=[...pending].reduce((a,b)=>(dist[a]??Infinity)<(dist[b]??Infinity)?a:b);if(!Number.isFinite(dist[u]))break;pending.delete(u);if(u===dest)break;
 for(const e of s.roads){if(e.status!=='OPEN'||(accessible&&!e.accessible)||(![e.u,e.v].includes(u)))continue;const a=s.nodes.find(n=>n.id===e.u),b=s.nodes.find(n=>n.id===e.v);if(s.hazards.some(h=>h.active&&intersects(a,b,h)))continue;const v=e.u===u?e.v:e.u,cost=dist[u]+e.distance*(1+e.risk*8);if(cost<(dist[v]??Infinity)){dist[v]=cost;prev[v]={u,edge:e.id};}}
 }
 if(!Number.isFinite(dist[dest]))return null;let path=[dest],edges=[];while(path[0]!==origin.id){let p=prev[path[0]];if(!p)return null;edges.unshift(p.edge);path.unshift(p.u);}const distance=edges.reduce((a,id)=>a+s.roads.find(e=>e.id===id).distance,0);return {path,edges,distance,cost:dist[dest],minutes:Math.ceil(distance/75),snapDistance:metres(position,origin)};
}
function options(s,p,accessible=false){return s.shelters.filter(a=>a.status==='OPEN'&&a.available>0&&(!accessible||a.accessible)&&!s.hazards.some(h=>h.active&&metres(a,h)<h.radius)).map(a=>({shelter:a,route:route(s,p,a.node,accessible)})).filter(a=>a.route).sort((a,b)=>a.route.cost-b.route.cost);}
const api={scenario,metres,intersects,route,options};if(typeof module!=='undefined')module.exports=api;root.Engine=api;
})(globalThis);
