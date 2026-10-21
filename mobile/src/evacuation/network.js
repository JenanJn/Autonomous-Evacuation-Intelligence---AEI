/** Real OSM road extraction and explicitly simulated disaster scenarios. */
const E = require('./engine');
const supported = ['Flood','Fire','Cyclone','Earthquake','Landslide'];
function emptyArea(point={lat:0,lon:0},type='Flood') {
 return {version:3,updated:new Date().toISOString(),simulated:true,networkSource:'OpenStreetMap',prepared:false,coverageRadius:1600,origin:point,nodes:[],roads:[],shelters:[],hazards:[{id:'H1',type,severity:'HIGH',...point,radius:100,active:false}],facilities:[],features:[],alerts:[]};
}
function offset(p,x,y){return {lat:p.lat+y/111320,lon:p.lon+x/(111320*Math.max(.05,Math.cos(p.lat*Math.PI/180)))};}
function makeHazards(area,type='Flood',growth=1){
 if(!supported.includes(type))throw Error('Choose a supported disaster.');
 if(!area.roads.length)return emptyArea(area.origin,type).hazards;
 const candidates=area.nodes.filter(n=>{const d=E.metres(n,area.origin);return d>400&&d<1300;});
 const center=candidates[Math.floor(candidates.length*.67)]||area.nodes[area.nodes.length-1];
 const radius=(type==='Cyclone'?160:type==='Fire'?100:75)*growth;
 let shape;
 if(type==='Cyclone')shape=[offset(center,-70,-220*growth),offset(center,180*growth,140*growth),offset(center,70*growth,240*growth),offset(center,-140*growth,180*growth),offset(center,-70,-220*growth)];
 else if(type==='Fire')shape=[offset(center,-radius,-radius*.5),offset(center,-radius*.45,radius),offset(center,radius*.6,radius*.75),offset(center,radius,radius*.1),offset(center,radius*.4,-radius),offset(center,-radius,-radius*.5)];
 else if(type==='Flood')shape=[offset(center,-radius*1.5,-radius*.6),offset(center,-radius*.8,radius),offset(center,radius*.3,radius*.6),offset(center,radius*1.6,-radius*.3),offset(center,radius*.5,-radius),offset(center,-radius*1.5,-radius*.6)];
 else if(type==='Landslide')shape=[offset(center,-radius,-radius),offset(center,-radius*.6,radius),offset(center,radius*.5,radius*.4),offset(center,radius,-radius*.6),offset(center,-radius,-radius)];
 return [{id:'H1',type,...center,radius,severity:'HIGH',active:true,shape,growth,description:type==='Earthquake'?'Simulated damage zone around the epicentre; rings are illustrative.':'Simulated affected area'}];
}
function buildArea(data,origin,type='Flood',mode='walking'){
 if(!Number.isFinite(origin.lat)||!Number.isFinite(origin.lon)||Math.abs(origin.lat)>85||Math.abs(origin.lon)>180)throw Error('Choose valid coordinates between 85°S and 85°N.');
 if(!Array.isArray(data.elements))throw Error('The road service returned an invalid response.');
 if(data.elements.length>80000)throw Error('This area is too dense for this prototype. Choose a nearby point or reduce the download radius.');
 const points=new Map(data.elements.filter(x=>x.type==='node'&&Number.isFinite(x.lat)&&Number.isFinite(x.lon)).map(n=>[n.id,{id:String(n.id),lat:n.lat,lon:n.lon}]));
 let roads=[];const features=[],pois=[];
 for(const item of data.elements){
  const t=item.tags||{},position=item.type==='node'?item:item.center;
  if(position&&['school','community_centre','townhall','place_of_worship','hospital','clinic'].includes(t.amenity))pois.push({...position,name:t.name||t.amenity.replace(/_/g,' '),type:t.amenity});
  if(item.type!=='way'||!Array.isArray(item.nodes))continue;
  const geometry=item.nodes.map(id=>points.get(id)).filter(Boolean);
  if(!t.highway){if(geometry.length>2&&features.length<1200&&(t.building||t.natural==='water'||t.waterway||t.leisure||t.landuse))features.push({id:String(item.id),kind:t.building?'building':t.natural==='water'||t.waterway?'water':'park',geometry});continue;}
  if(/^(construction|proposed|raceway)$/.test(t.highway)||t.area==='yes')continue;
  const restricted=/^(no|private)$/.test(t.access||'');
  const walking=!/^(motorway|motorway_link|trunk|trunk_link)$/.test(t.highway)&&!(/^(no|private)$/.test(t.foot||''))&&(!restricted||/^(yes|designated|permissive)$/.test(t.foot||''));
  const driving=!/^(footway|path|pedestrian|steps|cycleway|bridleway)$/.test(t.highway)&&!restricted&&!/^(no|private)$/.test(t.motor_vehicle||t.vehicle||'');
  if(!walking&&!driving)continue;
  for(let i=1;i<item.nodes.length;i++){
   const a=points.get(item.nodes[i-1]),b=points.get(item.nodes[i]);
   if(!a||!b||E.metres(a,origin)>1900||E.metres(b,origin)>1900)continue;
   const distance=E.metres(a,b);if(distance<.2)continue;
   const speed=parseFloat(t.maxspeed);const speedKph=Number.isFinite(speed)?Math.max(5,Math.min(100,speed*(/mph/.test(t.maxspeed)?1.609:1))):/^(primary|secondary|tertiary)/.test(t.highway)?35:20;
   roads.push({id:`W${item.id}:${i}`,u:a.id,v:b.id,distance,status:'OPEN',risk:0,accessible:t.highway!=='steps'&&t.wheelchair!=='no',walking,driving,oneway:t.oneway==='-1'?-1:t.oneway==='yes'||t.oneway==='1'||t.junction==='roundabout'?1:0,speedKph,name:t.name||t.ref||t.highway.replace(/_/g,' '),highway:t.highway,way:String(item.id)});
  }
 }
 if(roads.length<4)throw Error('Too few mapped public roads here. Choose a point near a road network. No artificial roads were generated.');
 const used=new Set(roads.flatMap(r=>[r.u,r.v]));let nodes=[...points.values()].filter(n=>used.has(n.id));
 const nearest=nodes.reduce((a,b)=>E.metres(a,origin)<E.metres(b,origin)?a:b);
 if(E.metres(nearest,origin)>350)throw Error('The selected point is too far from a mapped public road. Choose a point closer to a street.');
 const adjacency=new Map();for(const r of roads){if(!adjacency.has(r.u))adjacency.set(r.u,[]);if(!adjacency.has(r.v))adjacency.set(r.v,[]);adjacency.get(r.u).push(r.v);adjacency.get(r.v).push(r.u);}
 const connected=new Set([nearest.id]),queue=[nearest.id];for(let i=0;i<queue.length;i++)for(const id of adjacency.get(queue[i])||[])if(!connected.has(id)){connected.add(id);queue.push(id);}
 nodes=nodes.filter(n=>connected.has(n.id));roads=roads.filter(r=>connected.has(r.u)&&connected.has(r.v));
 if(nodes.length<6)throw Error('This local network is too small for an evacuation demonstration. Try another nearby road.');
 const area={...emptyArea(origin,type),prepared:true,nodes,roads,features,downloadedAt:new Date().toISOString()};
 const candidates=[];
 for(const poi of pois){const d=E.metres(poi,origin);if(d<250||d>1500)continue;const node=nodes.reduce((a,b)=>E.metres(a,poi)<E.metres(b,poi)?a:b);if(E.metres(node,poi)<180)candidates.push({node,name:`Demo · ${poi.name}`,address:`Training assembly point near mapped ${poi.type.replace(/_/g,' ')}; not a verified relief centre.`});}
 const intersections=nodes.filter(n=>(adjacency.get(n.id)||[]).length>=2&&E.metres(n,origin)>300&&E.metres(n,origin)<1400);
 intersections.sort((a,b)=>E.metres(a,origin)-E.metres(b,origin));
 for(let i=0;i<intersections.length;i+=Math.max(1,Math.floor(intersections.length/60)))candidates.push({node:intersections[i],name:'Demo assembly point',address:'Simulated assembly point on a real mapped street. Not a verified shelter.'});
 for(const c of candidates){if(area.shelters.length>=6)break;if(area.shelters.some(s=>E.metres(s,c.node)<220))continue;const index=area.shelters.length+1;area.shelters.push({...c.node,id:'S'+index,node:c.node.id,name:c.name==='Demo assembly point'?c.name+' '+index:c.name,capacity:200,available:200,status:'OPEN',medical:false,food:false,water:false,toilets:false,accessible:true,address:c.address,contact:'Demo facility — no real emergency contact',verified:false});}
 area.facilities=pois.filter(p=>['hospital','clinic'].includes(p.type)&&E.metres(p,origin)<1600).slice(0,12).map(p=>({lat:p.lat,lon:p.lon,name:p.name,type:p.type}));
 area.hazards=makeHazards(area,type);
 area.shelters=area.shelters.filter(s=>E.route(area,origin,s.node,false,mode));
 if(!area.shelters.length)throw Error('No demo destination is reachable in this downloaded area. Choose another point.');
 area.readiness={reachable:E.options(area,origin,false,mode).length,alternativeRoute:false};
 const first=E.options(area,origin,false,mode)[0];if(first){for(const edgeId of first.route.edges.slice(0,12)){const road=roads.find(r=>r.id===edgeId);road.status='BLOCKED';const alternative=E.route(area,origin,first.shelter.node,false,mode);road.status='OPEN';if(alternative){area.readiness.alternativeRoute=true;break;}}}
 return area;
}
module.exports={emptyArea,buildArea,makeHazards,offset};
