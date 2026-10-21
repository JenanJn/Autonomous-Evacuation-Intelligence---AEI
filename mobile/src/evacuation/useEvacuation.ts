import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, Linking, Share, Vibration } from 'react-native';
import { Audio } from 'expo-av';
import * as Location from 'expo-location';
import * as Network from 'expo-network';
import * as E from './engine';
import { emptyArea, makeHazards } from './network';
import { downloadArea } from './roads';
import { loadArea, saveArea } from './storage';
import { DisasterType } from './presentation';
export type Phase='overview'|'choose'|'preview'|'navigate'|'arrived'|'unavailable';
export type Notice={title:string;body:string;tone:'info'|'warning'|'danger'};
async function request(url:string,init:RequestInit={}){const c=new AbortController(),t=setTimeout(()=>c.abort(),12000);try{return await fetch(url,{...init,signal:c.signal});}finally{clearTimeout(t);}}
function useEvacuationState(){
 const [area,setArea]=useState<E.Area>(()=>emptyArea()),[position,setPosition]=useState<E.Point>(area.origin);
 const [source,setSource]=useState<'sample'|'saved'|'gps'|'manual'|'walk'>('sample');
 const [phase,setPhase]=useState<Phase>('overview'),[selectedId,setSelectedId]=useState<string|null>(null);
 const [accessible,setAccessible]=useState(false),[travelMode,setTravelMode]=useState<E.TravelMode>('walking');
 const [schematic,setSchematic]=useState(false),[gpsBusy,setGpsBusy]=useState(false),[loading,setLoading]=useState(false),[ready,setReady]=useState(false);
 const [storage,setStorage]=useState<'saving'|'saved'|'error'>('saved'),[connection,setConnection]=useState<'online'|'offline'|'unknown'>('unknown');
 const [notice,setNotice]=useState<Notice|null>(null),[revision,setRevision]=useState(0),[token,setToken]=useState(''),[rerouting,setRerouting]=useState(false);
 const [warning,setWarning]=useState<string|null>(null);
 const acknowledged=useRef('');
 const [eventLog,setEventLog]=useState<string[]>([]),[closureId,setClosureId]=useState<string|null>(null);
 const active=useRef(true),changed=useRef(false),latestArea=useRef(area),latestPosition=useRef(position),latestSource=useRef(source),watch=useRef<Location.LocationSubscription|null>(null);
 const download=useRef<AbortController|null>(null),rerouteTimer=useRef<ReturnType<typeof setTimeout>|null>(null),previous=useRef<{id:string;edges:string[]}|null>(null),saveQueue=useRef(Promise.resolve());
 latestArea.current=area;latestPosition.current=position;latestSource.current=source;
 const prepared=area.prepared===true&&area.nodes.length>0;
 const options=useMemo(()=>E.options(area,position,accessible,travelMode),[area,position,accessible,travelMode]);
 const selected=options.find(o=>o.shelter.id===selectedId)||null;
 const outside=prepared&&E.metres(position,area.origin)>(area.coverageRadius||1600);
 const backend=(process.env.EXPO_PUBLIC_DEMO_SERVER_URL||'').replace(/\/$/,'');
 useEffect(()=>{if(!warning)return;let sound:Audio.Sound|undefined,cancelled=false;
  void (async()=>{try{await Audio.setAudioModeAsync({playsInSilentModeIOS:true,staysActiveInBackground:false,shouldDuckAndroid:true});const result=await Audio.Sound.createAsync(require('../../assets/demo-alert.wav'),{shouldPlay:true,isLooping:true,volume:.45});sound=result.sound;if(cancelled)await sound.unloadAsync();}catch{/* The visible warning and vibration remain available. */}})();
  return()=>{cancelled=true;Vibration.cancel();if(sound)void sound.unloadAsync();};
 },[warning]);
 useEffect(()=>{const h=area.hazards.find(h=>h.active&&(h.shape?E.inside(position,h.shape):E.metres(position,h)<h.radius));if(!h)return;const key=[h.id,h.type,h.growth||1].join('|');if(acknowledged.current===key)return;acknowledged.current=key;setWarning('Your selected position is inside the simulated '+h.type.toLowerCase()+' area. Review the affected roads and evacuation options.');Vibration.vibrate([0,400,150,400]);},[area.hazards,position]);
 function log(message:string){setEventLog(old=>[`${new Date().toLocaleTimeString()} · ${message}`,...old].slice(0,12));}
 useEffect(()=>{active.current=true;loadArea().then(saved=>{if(saved?.prepared&&saved.networkSource==='OpenStreetMap'&&active.current&&!changed.current){setArea(saved);setPosition(saved.origin);setSource('saved');}}).catch(()=>{setNotice({title:'Saved area unavailable',body:'Choose a location and download its streets again.',tone:'warning'});}).finally(()=>{if(active.current)setReady(true);});return()=>{active.current=false;watch.current?.remove();download.current?.abort();if(rerouteTimer.current)clearTimeout(rerouteTimer.current);};},[]);
 useEffect(()=>{if(!ready||!prepared)return;let cancelled=false;setStorage('saving');saveQueue.current=saveQueue.current.catch(()=>{}).then(()=>saveArea(area));saveQueue.current.then(()=>{if(!cancelled)setStorage('saved');},()=>{if(!cancelled)setStorage('error');});return()=>{cancelled=true;};},[area,ready,prepared]);
 useEffect(()=>{function update(s:Network.NetworkState){if(active.current)setConnection(s.isConnected===false||s.isInternetReachable===false?'offline':s.isInternetReachable===true?'online':'unknown');}void Network.getNetworkStateAsync().then(update).catch(()=>{});const listener=Network.addNetworkStateListener(update);return()=>listener.remove();},[]);
 useEffect(()=>{const subscription=AppState.addEventListener('change',s=>{if(s!=='active'&&watch.current)setNotice({title:'Foreground navigation',body:'Keep AEI open for continuous GPS guidance. Map imagery opens in another app.',tone:'info'});});return()=>subscription.remove();},[]);
 useEffect(()=>{if(!backend||!prepared)return;let cancelled=false;async function sync(){try{const r=await request(backend+'/api/package');if(!r.ok)return;const d=await r.json();if(!cancelled&&d.revision>revision&&d.data?.networkSource==='OpenStreetMap'&&E.metres(d.data.origin,latestArea.current.origin)<100){setArea(d.data);setRevision(d.revision);log('New training update received');const alert=d.data.alerts?.[d.data.alerts.length-1];if(alert){setNotice({title:'Training alert',body:String(alert),tone:'warning'});setWarning(String(alert));Vibration.vibrate([0,300,150,300]);}}}catch{}}void sync();const timer=setInterval(sync,10000);return()=>{cancelled=true;clearInterval(timer);};},[backend,revision,prepared]);
 useEffect(()=>{
  if(phase!=='navigate'){previous.current=null;return;}if(rerouting)return;
  if(outside){setPhase('unavailable');setNotice({title:'Outside the downloaded area',body:'Download streets around your new location before continuing.',tone:'danger'});return;}
  if(!selected){if(options[0]){const next=options[0];setSelectedId(next.shelter.id);setNotice({title:'Destination changed',body:`The previous shelter is unreachable or full. Continue to ${next.shelter.name}: ${next.route.minutes} min, ${(next.route.distance/1000).toFixed(1)} km.`,tone:'warning'});log('Shelter fallback: '+next.shelter.name);Vibration.vibrate([0,150,100,150]);}else{setPhase('unavailable');setNotice({title:'No reachable shelter',body:'No available route remains in the downloaded data. Review SOS information.',tone:'danger'});log('No reachable shelter');}return;}
  const old=previous.current;if(old&&old.id===selected.shelter.id&&(old.edges.some(id=>area.roads.find(r=>r.id===id)?.status==='BLOCKED')||old.edges.slice(-selected.route.edges.length).join('|')!==selected.route.edges.join('|'))){setNotice({title:'Alternative route found',body:`Follow the updated route: ${selected.route.minutes} min · ${(selected.route.distance/1000).toFixed(1)} km.`,tone:'warning'});log('Recalculated route to '+selected.shelter.name);}
  previous.current={id:selected.shelter.id,edges:selected.route.edges};
  if((source==='gps'||source==='walk')&&E.metres(position,selected.shelter)<25&&selected.route.distance<40){setPhase('arrived');log('Arrived at demo destination');}
 },[phase,selected,options,outside,position,source,area,rerouting]);
 function mutate(update:(area:E.Area)=>void){changed.current=true;setArea(current=>{const next=JSON.parse(JSON.stringify(current)) as E.Area;update(next);next.version=(next.version||3)+1;next.updated=new Date().toISOString();return next;});}
 async function prepare(point:E.Point,type:DisasterType,origin:typeof source='manual'){
  download.current?.abort();const controller=new AbortController();download.current=controller;changed.current=true;setLoading(true);setNotice(null);setWarning(null);watch.current?.remove();watch.current=null;
  try{let next:E.Area;
   if(latestArea.current.prepared&&E.metres(point,latestArea.current.origin)<350){next=JSON.parse(JSON.stringify(latestArea.current));next.roads.forEach(r=>{r.status='OPEN';});next.hazards=makeHazards(next,type);}
   else {if(connection==='offline')throw Error('Internet is needed to download a new location. You can continue in your previously saved area.');next=await downloadArea(point,type,controller.signal,travelMode);}
   if(controller.signal.aborted||!active.current)return false;
   setArea(next);setPosition(point);setSource(origin);setPhase('overview');setSelectedId(null);previous.current=null;setEventLog([]);setClosureId(null);setSchematic(false);log('Prepared OpenStreetMap streets · '+type+' demo');
   const count=E.options(next,point,accessible,travelMode).length;
   if(count<2)setNotice({title:count?'Only one suitable destination':'No suitable destination',body:'The mapped network or this disaster limits reachable options. Choose another nearby point or transport mode; no roads were invented.',tone:'warning'});
   return true;
  }catch(error){if(!controller.signal.aborted&&active.current)setNotice({title:'Could not prepare this area',body:error instanceof Error?error.message:'Check connectivity and try again.',tone:'danger'});return false;}
  finally{if(download.current===controller&&active.current)setLoading(false);}
 }
 async function getGPS(){if((await Location.requestForegroundPermissionsAsync()).status!=='granted')throw Error('Allow location access or choose a point on the map.');const result=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High});return {lat:result.coords.latitude,lon:result.coords.longitude};}
 async function watchGPS(){watch.current?.remove();const sub=await Location.watchPositionAsync({accuracy:Location.Accuracy.High,distanceInterval:8,timeInterval:3000},r=>{if(active.current){setPosition({lat:r.coords.latitude,lon:r.coords.longitude});setSource('gps');}});if(active.current)watch.current=sub;else sub.remove();}
 async function startGPS(type:DisasterType){if(gpsBusy||loading)return false;setGpsBusy(true);try{const point=await getGPS();const ok=await prepare(point,type,'gps');if(ok)await watchGPS();return ok;}catch(error){setNotice({title:'GPS unavailable',body:error instanceof Error?error.message:'Try choosing a location on the map.',tone:'warning'});return false;}finally{setGpsBusy(false);}}
 async function locate(){if(gpsBusy||loading)return;setGpsBusy(true);try{const point=await getGPS();if(prepared&&E.metres(point,area.origin)<(area.coverageRadius||1600)){setPosition(point);setSource('gps');await watchGPS();}else{const ok=await prepare(point,area.hazards[0].type as DisasterType,'gps');if(ok)await watchGPS();}}catch(error){setNotice({title:'GPS unavailable',body:error instanceof Error?error.message:'Try again.',tone:'warning'});}finally{setGpsBusy(false);}}
 function cancelDownload(){download.current?.abort();setLoading(false);}
 function manual(point:E.Point){if(phase!=='navigate')void prepare(point,area.hazards[0].type as DisasterType,'manual');}
 function find(){if(!prepared||outside){setPhase('unavailable');return;}setNotice(null);setSelectedId(options[0]?.shelter.id||null);setPhase(options.length?'choose':'unavailable');}
 function select(id:string){setSelectedId(id);}
 function preview(id=selectedId){if(id&&options.some(o=>o.shelter.id===id)){setSelectedId(id);setPhase('preview');setNotice(null);}}
 function navigate(){if(selected&&!outside){setPhase('navigate');setNotice(null);log('Navigation started · '+selected.shelter.name);}}
 function stop(){setPhase('preview');setNotice(null);}
 function changeDisaster(type:DisasterType){if(!prepared)return;mutate(a=>{a.hazards=makeHazards(a,type);a.roads.forEach(r=>{r.status='OPEN';});});setSelectedId(null);setPhase('overview');setNotice(null);log(type+' scenario selected');}
 function blockAhead(isolate=false){
  if(!selected||rerouting||phase!=='navigate')return;
  let id=selected.route.edges[Math.min(1,selected.route.edges.length-1)];
  if(!isolate){for(const candidate of selected.route.edges.slice(1,20)){const next=JSON.parse(JSON.stringify(area)) as E.Area;next.roads.find(r=>r.id===candidate)!.status='BLOCKED';if(E.route(next,position,selected.shelter.node,accessible,travelMode)){id=candidate;break;}}}
  setClosureId(id);setRerouting(true);setNotice({title:'Road blocked ahead, rerouting…',body:'Updating the road network and checking reachable destinations.',tone:'danger'});Vibration.vibrate([0,200,100,200]);log('Road closure: '+id);
  // The closure is applied immediately; the short interval makes the calculation state visible.
  mutate(a=>a.roads.forEach(r=>{if(isolate?[r.u,r.v].includes(selected.shelter.node):r.id===id)r.status='BLOCKED';}));
  rerouteTimer.current=setTimeout(()=>{if(active.current)setRerouting(false);},900);
 }
 function demoStep(){if(!selected||rerouting)return;watch.current?.remove();watch.current=null;const points=selected.route.geometry||selected.route.path.map(id=>area.nodes.find(n=>n.id===id)!);const next=points.find(p=>E.metres(p,position)>5)||selected.shelter;setPosition(next);setSource('walk');}
 async function checkIn(id:string,count=1){const shelter=area.shelters.find(s=>s.id===id);if(!shelter)return;
  if(backend&&token){try{const r=await request(backend+'/api/check-in',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({shelter_id:id,count,origin:area.origin})});const data=await r.json();if(!r.ok)throw Error(data.error||'Check-in rejected');setArea(data.data);setRevision(data.revision);log('Server-confirmed check-in · '+shelter.name);return;}catch(error){setNotice({title:'Capacity update failed',body:error instanceof Error?error.message:'Retry when connected.',tone:'warning'});return;}}
  mutate(a=>{const s=a.shelters.find(s=>s.id===id)!;s.available=Math.max(0,Math.min(s.capacity,s.available-count));if(s.available===0)s.status='FULL';else if(s.status==='FULL')s.status='OPEN';});log(`${count>0?'Check-in':'Check-out'} · ${shelter.name} · ${Math.abs(count)} people`);}
 function advanceHazard(){mutate(a=>{a.hazards=makeHazards(a,a.hazards[0].type,(a.hazards[0].growth||1)+.35);});log('Disaster footprint expanded');}
 async function save(){if(!prepared)return;setStorage('saving');try{await saveArea(area);setStorage('saved');setNotice({title:'Street and routing data saved',body:'Actual street vectors, shelters and hazard geometry are stored locally. Detailed online tiles and imagery require connectivity.',tone:'info'});}catch{setStorage('error');}}
 async function login(password:string){try{if(!backend)return false;const r=await request(backend+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});if(!r.ok)return false;setToken((await r.json()).token);return true;}catch{return false;}}
 async function publish(alert:string){if(!backend||!token)return false;try{const updated={...area,alerts:alert.trim()?[...area.alerts,alert.trim().slice(0,500)]:area.alerts};const r=await request(backend+'/api/package',{method:'PUT',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify(updated)});if(!r.ok)return false;setRevision((await r.json()).revision);setArea(updated);return true;}catch{return false;}}
 async function shareLocation(){try{await Share.share({message:`${source==='gps'?'My GPS location':'Selected/demo location'}: ${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}`});}catch{setNotice({title:'Sharing unavailable',body:'Read your coordinates from SOS.',tone:'info'});}}
 async function surroundings(){try{await Linking.openURL(`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${position.lat}%2C${position.lon}`);}catch{setNotice({title:'Imagery unavailable',body:'Street imagery opens in Google Maps where coverage exists and needs internet.',tone:'info'});}}
 return {area,position,source,phase,setPhase,selected,selectedId,options,accessible,setAccessible,travelMode,setTravelMode,schematic,setSchematic,gpsBusy,loading,ready,prepared,storage,connection,notice,setNotice,outside,backend,token,revision,rerouting,closureId,eventLog,warning,dismissWarning:()=>setWarning(null),mutate,prepare,cancelDownload,startGPS,locate,manual,find,select,preview,navigate,stop,changeDisaster,blockAhead,demoStep,checkIn,advanceHazard,save,login,publish,shareLocation,surroundings,guidance:rerouting?{symbol:'!',instruction:'Road blocked ahead',next:'Recalculating your route…'}:E.guidance(area,selected?.route||null)};
}
export type EvacuationModel=ReturnType<typeof useEvacuationState>;
const Context=createContext<EvacuationModel|null>(null);
export function EvacuationProvider({children}:{children:React.ReactNode}){return React.createElement(Context.Provider,{value:useEvacuationState()},children);}
export function useEvacuation(){const model=useContext(Context);if(!model)throw Error('EvacuationProvider is missing');return model;}
