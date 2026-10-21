const assert=require('node:assert/strict');
const E=require('../../mobile/src/evacuation/engine');
const N=require('../../mobile/src/evacuation/network');
// Small OSM-format fixture for network semantics; never shipped as an app location.
function fixture(lat,lon){const elements=[];let id=1;for(let y=0;y<4;y++)for(let x=0;x<4;x++)elements.push({type:'node',id:id++,lat:lat+y*.002,lon:lon+x*.002});let way=100;for(let y=0;y<4;y++)elements.push({type:'way',id:way++,nodes:[1+y*4,2+y*4,3+y*4,4+y*4],tags:{highway:'residential',name:'Street '+y}});for(let x=0;x<4;x++)elements.push({type:'way',id:way++,nodes:[1+x,5+x,9+x,13+x],tags:{highway:'residential',name:'Avenue '+x}});return {elements};}
for(const origin of [{lat:12,lon:77},{lat:51,lon:-2},{lat:-30,lon:150}]){
 const a=N.buildArea(fixture(origin.lat,origin.lon),origin,'Flood');assert.equal(a.networkSource,'OpenStreetMap');assert(a.roads.every(r=>r.id.startsWith('W')));assert(a.nodes.every(n=>fixture(origin.lat,origin.lon).elements.some(e=>String(e.id)===n.id)));assert(a.shelters.length>=2);assert(a.features);assert(a.shelters.every(s=>s.verified===false));
 for(const type of ['Flood','Fire','Cyclone','Earthquake','Landslide']){a.hazards=N.makeHazards(a,type);assert.equal(a.hazards[0].type,type);assert(type==='Earthquake'||a.hazards[0].shape.length>=4);}
 a.hazards=[];const opts=E.options(a,origin);assert(opts.length>=2);const best=opts[0],blocked=best.route.edges[0];a.roads.find(r=>r.id===blocked).status='BLOCKED';const reroute=E.route(a,origin,best.shelter.node);assert(reroute);assert(!reroute.edges.includes(blocked));assert.notDeepEqual(reroute.edges,best.route.edges);
 best.shelter.available=0;assert(!E.options(a,origin).some(o=>o.shelter.id===best.shelter.id));
}
const s=N.buildArea(fixture(12,77),{lat:12,lon:77});s.hazards=[];
const r=E.route(s,s.nodes[0],s.nodes[3].id);assert(r.geometry.length>1);assert.equal(E.guidance(s,r).instruction.split(' ')[1],'east');assert.equal(E.guidance(s,E.route(s,s.nodes[3],s.nodes[0].id)).instruction.split(' ')[1],'west');
const polygon=[{lat:0,lon:0},{lat:0,lon:1},{lat:1,lon:1},{lat:1,lon:0}];assert(E.intersects({lat:.5,lon:-.5},{lat:.5,lon:1.5},{shape:polygon}));assert(!E.intersects({lat:2,lon:0},{lat:2,lon:1},{shape:polygon}));
const one={...N.emptyArea({lat:0,lon:0}),nodes:[{id:'a',lat:0,lon:0},{id:'b',lat:0,lon:.001}],roads:[{id:'r',u:'a',v:'b',distance:111,status:'OPEN',accessible:true,walking:true,driving:true,oneway:1,risk:0}],hazards:[]};
assert(E.route(one,one.nodes[0],'b',false,'driving'));assert.equal(E.route(one,one.nodes[1],'a',false,'driving'),null);assert(E.route(one,one.nodes[1],'a',false,'walking'));
one.roads[0].walking=false;assert.equal(E.route(one,one.nodes[0],'b',false,'walking'),null);
assert.throws(()=>N.buildArea({elements:[]},{lat:12,lon:77}),/Too few/);
console.log('PASS: no fixed location, real OSM node/edge identity, five hazard geometries, actual alternative-route search, capacity exclusion, east/west guidance, polygon intersections, transport and one-way restrictions, insufficient coverage errors');
