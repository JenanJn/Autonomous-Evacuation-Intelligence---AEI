const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../../mobile/node_modules/typescript');
const source=fs.readFileSync(path.join(__dirname,'../../mobile/src/evacuation/presentation.ts'),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const moduleContext={exports:{}};vm.runInNewContext(compiled,{module:moduleContext,exports:moduleContext.exports});
const P=moduleContext.exports,E=require('../../mobile/src/evacuation/engine.js');
const types=['Flood','Fire','Cyclone','Earthquake','Landslide'];
assert.equal(new Set(types.map(type=>P.disasterVisual(type).color)).size,5);
assert.equal(new Set(types.map(type=>P.disasterVisual(type).zone)).size,5);
assert.equal(P.disasterVisual('Flood').texture,'≋');assert.equal(P.disasterVisual('Fire').texture,'🔥');
for(const type of types){const area=E.scenario(13.0827,80.2707,type),h=area.hazards[0];assert(P.disasterVisual(type).advice.length>20);for(const p of P.hazardTexturePoints(h))assert(E.metres(p,h)<h.radius);}
const area=E.scenario(),option=E.options(area,area.origin)[0];
assert(P.routeGuidance(area,option.route).instruction.startsWith('Head '));
assert.equal(P.routeGuidance(area,null).instruction,'Shelter is ahead');
area.roads[0].status='BLOCKED';assert(P.routeSummary(area).includes('1 closed road'));
console.log('PASS: five distinct disaster visuals, flood/water and fire/flame textures, symbols inside hazard extents, guidance, route explanation');
