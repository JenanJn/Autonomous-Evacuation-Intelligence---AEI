import { LEAFLET_CSS, LEAFLET_JS } from './leafletVendor';
import { disasterVisual, hazardTexturePoints } from '../presentation';
import { inside } from '../engine';
import type { MapProps } from './mapTypes';

/** Only JSON crosses the native bridge; callbacks and executable strings never do. */
export function mapSnapshot(p: MapProps) {
  return {
    area: p.area, position: p.position, positionLabel: p.positionLabel,
    selectedId: p.selectedId, route: p.route, schematic: p.schematic,
    bottomSpace: p.bottomSpace, navigating: p.navigating, focusRoute: p.focusRoute,
    compact: p.compact||p.navigating||p.focusRoute, picking:p.picking, worldView:p.worldView,
    hazards: p.area.hazards.filter(h => h.active).map(h => ({
      ...h, visual: disasterVisual(h.type), textures: hazardTexturePoints(h).filter(point=>!h.shape||inside(point,h.shape)),
    })),
  };
}
export type MapSnapshot = ReturnType<typeof mapSnapshot>;
export const MAP_BASE_URL = 'https://github.com/JenanJn/Autonomous-Evacuation-Intelligence-or-AEI-./';
export const MAP_DOCUMENT = `<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: https://tile.openstreetmap.org; base-uri 'none'; form-action 'none'">
<style>${LEAFLET_CSS}
html,body,#map{width:100%;height:100%;margin:0;overflow:hidden;font-family:Arial,sans-serif}
#map{background-color:#e6eee8;background-image:none}
.street-label{display:block;font-size:10px;line-height:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:115px;color:#67796d;text-shadow:0 1px white,1px 0 white,0 -1px white,-1px 0 white;text-align:center}.aei-icon{background:none;border:0}.pin{display:flex;align-items:center;justify-content:center;min-width:42px;height:34px;border:2px solid #087457;border-radius:13px;background:white;color:#087457;font-size:19px;font-weight:800;box-sizing:border-box;box-shadow:0 2px 4px #183b2620}
.pin.selected{background:#087457;color:white}.pin.closed{border-color:#c33b30;color:#c33b30;background:#fff0ed}
.map-name{position:absolute;left:50%;transform:translateX(-50%);top:38px;white-space:nowrap;background:#fffffff2;border-radius:4px;padding:3px;font-size:10px;color:#25473d;font-weight:700}
.hazard-label{position:absolute;bottom:0;left:50%;transform:translateX(-50%);white-space:nowrap;border:1px solid;border-radius:8px;padding:6px 8px;font-size:10px;font-weight:800}
.you{height:36px;width:36px;border-radius:50%;background:#227de633;display:grid;place-items:center}.you:after{content:'';width:14px;height:14px;border-radius:50%;background:#237ce0;border:3px solid white}
.texture{display:block;text-align:center;font-weight:bold;line-height:40px}.medical{display:grid;place-items:center;background:white;border:1px solid #b7caca;border-radius:8px;color:#628d9d;font-size:25px;height:28px;width:28px}.closed-road{display:grid;place-items:center;border-radius:50%;width:24px;height:24px;background:#bc3026;color:white;border:2px solid white;font-size:24px;line-height:24px}
#credit,#status{position:absolute;z-index:900;background:#fffffff2;color:#36584a;border-radius:5px;padding:4px 6px;font-size:10px;line-height:14px}
#credit{right:6px}#credit a{color:#36584a}#status{left:12px;max-width:220px;pointer-events:none}#status:empty{display:none}
.leaflet-control-zoom{border:1px solid #cfdbd3!important;border-radius:12px!important;overflow:hidden}.leaflet-control-zoom a{width:38px!important;height:38px!important;line-height:38px!important;color:#24473b!important}
.leaflet-bottom.leaflet-left{left:3px}.leaflet-tile{filter:saturate(.65)}
</style></head><body><div id="map" role="region" aria-label="Evacuation map"></div>
<div id="status" role="status"></div><div id="credit">© <a id="license" href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a></div>
<script>${LEAFLET_JS.replace(/<\/script/gi, '<\\/script')}</script><script>
(function(){
 'use strict';
 var state=null,signature='',tiles=null,failed=0,loaded=0,tileTimer=null,follow=true;
 var status=document.getElementById('status');var baseVisible=null;
 function emit(message){if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage(JSON.stringify(message));else if(window.parent!==window)window.parent.postMessage({aeiMap:true,...message},'*');}
 function escape(value){return String(value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
 function ll(point){return [point.lat,point.lon];}
 var map=L.map('map',{zoomControl:false,attributionControl:false,minZoom:3,maxZoom:19,zoomSnap:.25,fadeAnimation:false,preferCanvas:true}).setView([0,0],2);
 L.control.zoom({position:'bottomleft'}).addTo(map);
 var base=L.layerGroup().addTo(map);var roads=L.layerGroup().addTo(map),zones=L.layerGroup().addTo(map),routes=L.layerGroup().addTo(map),markers=L.layerGroup().addTo(map);
 function tileStatus(){if(!state)return;renderBase(false);status.textContent=state.schematic?'Offline streets · downloaded data':failed>0&&loaded===0?'Street map unavailable · downloaded streets shown':failed>0?'Some streets unavailable · downloaded streets retained':loaded===0?'Loading streets · downloaded streets shown':'';}
 function tileMode(){
  if(state.schematic){if(tiles){tiles.off();map.removeLayer(tiles);tiles=null;}clearTimeout(tileTimer);failed=0;loaded=0;tileStatus();return;}
  if(tiles){tileStatus();return;}
  failed=0;loaded=0;
  tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,keepBuffer:0,updateWhenIdle:true,updateWhenZooming:false,crossOrigin:false});
  tiles.on('tileload',function(){loaded++;tileStatus();});
  tiles.on('tileerror',function(){failed++;tileStatus();});
  tiles.addTo(map);tileStatus();
  tileTimer=setTimeout(function(){if(!loaded&&state&&!state.schematic){failed++;tileStatus();}},10000);
 }
 function marker(point,html,size,anchor,title,click,z){
  var item=L.marker(ll(point),{icon:L.divIcon({className:'aei-icon',html:html,iconSize:size,iconAnchor:anchor}),title:title||'',keyboard:!!click,interactive:!!click,zIndexOffset:z||0}).addTo(markers);
  if(click)item.on('click',click);return item;
 }
 function points(){
  var result=[ll(state.position)];
  if(!state.focusRoute)state.area.shelters.forEach(function(s){result.push(ll(s));});
  state.hazards.forEach(function(h){result.push(ll(h));result.push([h.lat+h.radius/111320,h.lon]);result.push([h.lat-h.radius/111320,h.lon]);});
  if(state.route&&state.focusRoute)(state.route.geometry||state.route.path.map(function(id){return state.area.nodes.find(function(n){return n.id===id;});})).forEach(function(n){if(n)result.push(ll(n));});
  return result;
 }
 function fit(){if(!state)return;map.invalidateSize({pan:false});if(state.picking){map.setView(state.worldView?[0,0]:ll(state.position),state.worldView?2:15,{animate:false});return;}if(!state.area.prepared){map.setView([0,0],2,{animate:false});return;}map.fitBounds(points(),{paddingTopLeft:[35,state.navigating?160:132],paddingBottomRight:[35,state.bottomSpace+35],maxZoom:17,animate:false});follow=true;}
 function renderBase(force){
  if(!state)return;var visible=state.schematic||loaded===0;if(!force&&baseVisible===visible)return;baseVisible=visible;base.clearLayers();if(!visible)return;
  (state.area.features||[]).forEach(function(f){var color=f.kind==='water'?'#b6dbe9':f.kind==='park'?'#cde2c8':'#d5dcd3';L.polygon(f.geometry.map(ll),{color:color,weight:1,fillColor:color,fillOpacity:.8,interactive:false}).addTo(base);});
  var nodes={};state.area.nodes.forEach(function(n){nodes[n.id]=n;});var groups={};
  state.area.roads.forEach(function(r){if(!nodes[r.u]||!nodes[r.v])return;var key=r.way||r.id;if(!groups[key])groups[key]={parts:[],last:null,name:r.name,highway:r.highway};var g=groups[key];if(g.last!==r.u)g.parts.push([ll(nodes[r.u])]);g.parts[g.parts.length-1].push(ll(nodes[r.v]));g.last=r.v;});
  var labels=0;Object.keys(groups).forEach(function(key){var g=groups[key];g.parts.forEach(function(line){var width=/^(primary|secondary|tertiary)/.test(g.highway||'')?9:6;L.polyline(line,{color:'#c3cec4',weight:width,interactive:false}).addTo(base);L.polyline(line,{color:'#ffffff',weight:width-2,interactive:false}).addTo(base);if(g.name&&line.length>3&&labels<28){labels++;L.marker(line[Math.floor(line.length/2)],{icon:L.divIcon({className:'aei-icon',html:'<span class="street-label">'+escape(g.name)+'</span>',iconSize:[115,14],iconAnchor:[57,7]}),interactive:false,keyboard:false}).addTo(base);}});});
 }
 function render(){
  roads.clearLayers();zones.clearLayers();routes.clearLayers();markers.clearLayers();renderBase(true);
  var nodes={};state.area.nodes.forEach(function(n){nodes[n.id]=n;});
  state.area.roads.forEach(function(r){if(!nodes[r.u]||!nodes[r.v])return;var blocked=r.status==='BLOCKED';if(!blocked)return;L.polyline([ll(nodes[r.u]),ll(nodes[r.v])],{color:blocked?'#c33b30':'#849e93',weight:blocked?5:2,opacity:blocked?1:.75,dashArray:blocked?'7 6':undefined,interactive:false}).addTo(roads);
   if(blocked)marker({lat:(nodes[r.u].lat+nodes[r.v].lat)/2,lon:(nodes[r.u].lon+nodes[r.v].lon)/2},'<span class="closed-road">×</span>',[28,28],[14,14],'Road blocked',null,60);
  });
  (state.picking?[]:state.hazards).forEach(function(h){var v=h.visual;
   var style={color:v.color,weight:2,fillColor:v.color,fillOpacity:.22};
   (h.shape?L.polygon(h.shape.map(ll),style):L.circle(ll(h),Object.assign({radius:h.radius},style))).addTo(zones).on('click',function(){emit({type:'hazard'});});
   if(h.type==='Earthquake'){[1.7,2.5].forEach(function(factor){L.circle(ll(h),{radius:h.radius*factor,color:v.color,weight:1,dashArray:'5 7',fill:false,interactive:false}).addTo(zones);});}
   if(h.type==='Cyclone')L.polyline([ll({lat:h.lat-.002,lon:h.lon-.0007}),ll(h),ll({lat:h.lat+.002,lon:h.lon+.0007})],{color:v.color,dashArray:'6 5',weight:2,interactive:false}).addTo(zones);
   h.textures.forEach(function(p){marker(p,'<span class="texture" style="font-size:'+(h.type==='Flood'?34:24)+'px;color:'+v.color+'">'+escape(v.texture)+'</span>',[40,40],[20,20],v.zone,null,-300);});
   marker({lat:h.lat+h.radius/111320,lon:h.lon},'<span class="hazard-label" style="background:'+v.background+';border-color:'+v.color+';color:'+v.color+'">'+escape(v.icon)+' '+escape(v.zone)+'</span>',[0,0],[0,0],v.zone,function(){emit({type:'hazard'});},10);
  });
  if(state.route&&!state.picking){var path=(state.route.geometry||state.route.path.filter(function(id){return nodes[id];}).map(function(id){return nodes[id];})).map(ll);L.polyline(path,{color:'white',weight:11,interactive:false}).addTo(routes);L.polyline(path,{color:'#087457',weight:6,interactive:false}).addTo(routes);}
  (state.picking?[]:state.area.facilities).forEach(function(f){marker(f,'<span class="medical">+</span>',[28,28],[14,14],f.name+' · simulated',null,-100);});
  (state.picking?[]:state.area.shelters).forEach(function(s,i){var open=s.status==='OPEN'&&s.available>0,selected=state.selectedId===s.id;
   marker(s,'<span class="pin '+(!open?'closed':selected?'selected':'')+'">⌂ '+(i+1)+'</span>'+(!state.compact?'<span class="map-name">'+escape(s.name)+'</span>':''),[48,38],[24,19],s.name,function(){emit({type:'shelter',id:s.id});},selected?200:100);
  });
  marker(state.position,'<span class="you"></span>',[36,36],[18,18],state.positionLabel,null,1000);
 }
 window.AEIMap={update:function(next){
  if(!next.area&&state)next.area=state.area;if(!next.area)return;
  var nextSignature=JSON.stringify([next.area.origin,next.picking,next.worldView,next.picking?next.position:null,next.selectedId,next.route&&next.route.path,next.focusRoute,next.navigating,next.bottomSpace,next.hazards.map(function(h){return [h.id,h.lat,h.lon,h.radius,h.type];})]);
  var moved=state&&(state.position.lat!==next.position.lat||state.position.lon!==next.position.lon);
  state=next;document.getElementById('credit').style.bottom=(next.bottomSpace+3)+'px';status.style.bottom=(next.bottomSpace+57)+'px';document.querySelector('.leaflet-bottom.leaflet-left').style.bottom=(next.picking?14:next.bottomSpace+91)+'px';if(next.picking)status.style.bottom='60px';
  render();
  if(nextSignature!==signature){signature=nextSignature;fit();}else if(moved&&next.navigating&&follow){var center=map.latLngToContainerPoint(ll(next.position));map.panBy([center.x-map.getSize().x/2,center.y-(132+(map.getSize().y-next.bottomSpace-132)/2)],{animate:false});}
  tileMode();
 },overview:fit,focus:function(point){if(!state)return;follow=true;var pos=point||state.position;map.setView(ll(pos),Math.max(15,map.getZoom()),{animate:false});var visibleY=132+(map.getSize().y-state.bottomSpace-132)/2;map.panBy([0,map.getSize().y/2-visibleY],{animate:false});}};
 map.on('dragstart',function(){follow=false;emit({type:'pan'});});
 map.on('click',function(e){if(state&&state.picking)emit({type:'manual',point:{lat:e.latlng.lat,lon:e.latlng.lng}});});
 map.on('contextmenu',function(e){if(state&&state.picking)emit({type:'manual',point:{lat:e.latlng.lat,lon:e.latlng.lng}});});
 window.addEventListener('message',function(e){if(e.source!==window.parent||!e.data||!e.data.aeiCommand)return;var c=e.data;if(c.type==='update')window.AEIMap.update(c.payload);else if(c.type==='focus')window.AEIMap.focus(c.point);else if(c.type==='overview')fit();});
 window.addEventListener('resize',function(){map.invalidateSize({pan:false});fit();});
 document.getElementById('license').addEventListener('click',function(e){e.preventDefault();emit({type:'license'});});
 emit({type:'ready'});
})();
</script></body></html>`;
