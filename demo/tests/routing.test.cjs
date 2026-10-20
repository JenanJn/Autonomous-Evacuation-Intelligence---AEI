const assert=require('node:assert/strict');const E=require(process.argv[2]||'../web/engine.js');
let s=E.scenario(12.97,77.59),p=s.origin,options=E.options(s,p);assert(options.length>=2);assert(s.hazards[0].lat>12.97);let first=options[0];
for(const id of first.route.edges){let e=s.roads.find(e=>e.id===id);assert(!s.hazards.some(h=>E.intersects(s.nodes.find(n=>n.id===e.u),s.nodes.find(n=>n.id===e.v),h)));}
s.roads.find(e=>e.id===first.route.edges[0]).status='BLOCKED';let alternate=E.route(s,p,first.shelter.node);assert(alternate);assert(!alternate.edges.includes(first.route.edges[0]));
s.roads.filter(e=>[e.u,e.v].includes(first.shelter.node)).forEach(e=>e.status='BLOCKED');assert.equal(E.route(s,p,first.shelter.node),null);assert(!E.options(s,p).some(o=>o.shelter.id===first.shelter.id));
s.shelters.forEach(s=>s.status='CLOSED');assert.equal(E.options(s,p).length,0);
s=E.scenario();s.shelters[0].available=0;assert(!E.options(s,s.origin).some(o=>o.shelter.id==='S1'));s.roads.forEach(e=>e.accessible=false);assert.equal(E.options(s,s.origin,true).length,0);
console.log('PASS: location anchoring, multiple shelters, hazard exclusion, alternative route, unreachable fallback, closures, capacity, accessibility');
