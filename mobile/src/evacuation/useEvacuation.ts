import { useEffect, useMemo, useRef, useState } from 'react';
import { AppState, Share } from 'react-native';
import * as Location from 'expo-location';
import * as Network from 'expo-network';
import * as E from './engine';
import { loadArea, saveArea } from './storage';
import { DisasterType, routeGuidance } from './presentation';
export type Phase = 'overview' | 'choose' | 'preview' | 'navigate' | 'arrived' | 'unavailable';
export type Notice = { title: string; body: string; tone: 'info' | 'warning' | 'danger' };
async function request(url: string, init: RequestInit = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try { return await fetch(url, { ...init, signal: controller.signal }); }
  finally { clearTimeout(timeout); }
}
export function useEvacuation() {
  const [area, setArea] = useState<E.Area>(() => E.scenario());
  const [position, setPosition] = useState<E.Point>(area.origin);
  const [source, setSource] = useState<'sample' | 'saved' | 'gps' | 'manual' | 'walk'>('sample');
  const [phase, setPhase] = useState<Phase>('overview');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [accessible, setAccessible] = useState(false);
  const [schematic, setSchematic] = useState(false);
  const [gpsBusy, setGpsBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [storage, setStorage] = useState<'saving' | 'saved' | 'error'>('saving');
  const [connection, setConnection] = useState<'online' | 'offline' | 'unknown'>('unknown');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [revision, setRevision] = useState(0);
  const [token, setToken] = useState('');
  const active = useRef(true), changed = useRef(false);
  const watch = useRef<Location.LocationSubscription | null>(null);
  const latestArea = useRef(area), latestPosition = useRef(position);
  const previousRoute = useRef<{id: string; edges: string[]} | null>(null);
  const saveQueue = useRef(Promise.resolve());
  latestArea.current = area; latestPosition.current = position;
  const options = useMemo(() => E.options(area, position, accessible), [area, position, accessible]);
  const selected = options.find(o => o.shelter.id === selectedId) || null;
  const outside = E.metres(position, area.origin) > 2000;
  const backend = (process.env.EXPO_PUBLIC_DEMO_SERVER_URL || '').replace(/\/$/, '');
  useEffect(() => {
    active.current = true;
    loadArea().then(saved => {
      if (active.current && saved && !changed.current) {
        setArea(saved); setPosition(saved.origin); setSource('saved');
      }
    }).catch(() => {
      if (active.current) setNotice({ title: 'Offline data could not be loaded', body: 'A sample training area is shown. Use your location to start again.', tone: 'warning' });
    }).finally(() => { if (active.current) setReady(true); });
    return () => { active.current = false; watch.current?.remove(); };
  }, []);
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setStorage('saving');
    saveQueue.current = saveQueue.current.catch(() => {}).then(() => saveArea(area));
    saveQueue.current.then(() => { if (!cancelled) setStorage('saved'); }, () => { if (!cancelled) setStorage('error'); });
    return () => { cancelled = true; };
  }, [area, ready]);
  useEffect(() => {
    function update(state: Network.NetworkState) {
      if (!active.current) return;
      setConnection(state.isConnected === false || state.isInternetReachable === false ? 'offline' : state.isInternetReachable === true ? 'online' : 'unknown');
    }
    void Network.getNetworkStateAsync().then(update).catch(() => {});
    const listener = Network.addNetworkStateListener(update);
    return () => listener.remove();
  }, []);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (state !== 'active' && watch.current) setNotice({title:'Keep AEI open for navigation',body:'Location guidance works while the app is on screen. Recheck your GPS when you return.',tone:'info'});
    });
    return () => subscription.remove();
  }, []);
  useEffect(() => {
    if (!backend) return;
    let cancelled = false;
    async function sync() {
      try {
        const response = await request(backend + '/api/package');
        if (!response.ok) return;
        const data = await response.json();
        if (!cancelled && data.data?.simulated === true && Array.isArray(data.data.roads) && data.revision > revision && E.metres(data.data.origin, latestArea.current.origin) < 100) {
          setArea(data.data); setRevision(data.revision);
          const alert = data.data.alerts?.[data.data.alerts.length - 1];
          if (typeof alert === 'string') setNotice({title:'Training update',body:alert,tone:'warning'});
        }
      } catch { /* The local route and offline package remain available. */ }
    }
    void sync(); const timer = setInterval(sync, 10000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [backend, revision]);
  useEffect(() => {
    if (phase !== 'navigate') { previousRoute.current = null; return; }
    if (outside) {
      setPhase('unavailable'); setSelectedId(null);
      setNotice({title:'Outside the saved area',body:'Navigation has stopped. Refresh your location to prepare a new training area.',tone:'danger'});
      return;
    }
    if (!selected) {
      if (options[0]) {
        setSelectedId(options[0].shelter.id);
        setNotice({title:'Changing your shelter',body:`The previous shelter cannot be reached. Navigation is switching to ${options[0].shelter.name}.`,tone:'warning'});
      } else {
        setPhase('unavailable'); setSelectedId(null);
        setNotice({title:'No reachable shelter',body:'Navigation has stopped. Open SOS for your location and stored emergency information.',tone:'danger'});
      }
      return;
    }
    const old = previousRoute.current;
    if (old?.id === selected.shelter.id && old.edges.some(id => area.roads.find(r => r.id === id)?.status === 'BLOCKED')) {
      setNotice({title:'Road closed · route updated',body:'An alternative route to your shelter is now shown. Follow the green line.',tone:'warning'});
    }
    previousRoute.current = {id:selected.shelter.id,edges:selected.route.edges};
    if ((source === 'gps' || source === 'walk') && E.metres(position, selected.shelter) < 45) setPhase('arrived');
  }, [phase, selected, options, outside, position, source, area]);
  function mutate(update: (area: E.Area) => void) {
    changed.current = true;
    setArea(current => { const next = JSON.parse(JSON.stringify(current)) as E.Area; update(next); next.updated = new Date().toISOString(); return next; });
  }
  function replaceAt(point: E.Point, type: string, origin: typeof source) {
    changed.current = true; setArea(E.scenario(point.lat, point.lon, type));
    setPosition(point); setSource(origin); setPhase('overview'); setSelectedId(null); setNotice(null);
  }
  async function locate() {
    if (!ready || gpsBusy) return;
    setGpsBusy(true);
    try {
      if ((await Location.requestForegroundPermissionsAsync()).status !== 'granted') {
        setNotice({title:'Location access is off',body:'Allow location in phone settings, or explore the labeled demo area.',tone:'warning'}); return;
      }
      watch.current?.remove(); watch.current = null;
      const result = await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High});
      if (!active.current) return;
      replaceAt({lat:result.coords.latitude,lon:result.coords.longitude},latestArea.current.hazards[0].type,'gps');
      const subscription = await Location.watchPositionAsync({accuracy:Location.Accuracy.High,distanceInterval:8,timeInterval:3000}, result => {
        if (active.current) { setPosition({lat:result.coords.latitude,lon:result.coords.longitude}); setSource('gps'); }
      });
      if (active.current) watch.current = subscription; else subscription.remove();
    } catch {
      if (active.current) setNotice({title:'GPS is unavailable',body:'Check phone location services and try again. Your saved training area remains available.',tone:'warning'});
    } finally { if (active.current) setGpsBusy(false); }
  }
  function manual(point: E.Point) {
    if (phase === 'navigate') return;
    watch.current?.remove(); watch.current = null;
    replaceAt(point, area.hazards[0].type, 'manual');
  }
  function find() {
    if (outside) { setPhase('unavailable'); return; }
    setNotice(null); setSelectedId(options[0]?.shelter.id || null);
    setPhase(options.length ? 'choose' : 'unavailable');
  }
  function select(id:string) { setSelectedId(id); }
  function preview(id = selectedId) {
    if (!id || !options.some(o => o.shelter.id === id)) return;
    setSelectedId(id); setPhase('preview'); setNotice(null);
  }
  function navigate() { if (selected && !outside) { setPhase('navigate'); setNotice(null); } }
  function stop() { setPhase('preview'); setNotice(null); }
  function changeDisaster(type:DisasterType) { replaceAt(position,type,source); }
  function blockAhead(isolate = false) {
    if (!selected) return;
    mutate(next => next.roads.forEach(road => {
      if (isolate ? [road.u,road.v].includes(selected.shelter.node) : road.id === selected.route.edges[0]) road.status = 'BLOCKED';
    }));
    setNotice({title:'Road closure received',body:'Checking another route and alternative shelters.',tone:'warning'});
  }
  function demoStep() {
    if (!selected) return;
    watch.current?.remove(); watch.current = null;
    const node = area.nodes.find(n => n.id === (selected.route.path[1] || selected.route.path[0]));
    if (node) { setPosition(node); setSource('walk'); }
  }
  async function save() {
    setStorage('saving');
    try { await saveArea(area); setStorage('saved'); setNotice({title:'Route data saved on this phone',body:'Shelters, hazards and route calculations work offline. Use the schematic map when the street basemap is unavailable.',tone:'info'}); }
    catch { setStorage('error'); setNotice({title:'Could not save offline data',body:'Check free device storage and try again.',tone:'danger'}); }
  }
  async function login(password:string) {
    try {
      if (!backend) throw Error('No server');
      const response = await request(backend+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
      if (!response.ok) throw Error('Rejected');
      setToken((await response.json()).token);
      return true;
    } catch { return false; }
  }
  async function publish(alert:string) {
    if (!backend || !token) return false;
    try {
      const updated = {...area,alerts:alert.trim()?[...area.alerts,alert.trim().slice(0,500)]:area.alerts};
      const response = await request(backend+'/api/package',{method:'PUT',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify(updated)});
      if (!response.ok) return false;
      setRevision((await response.json()).revision); setArea(updated); return true;
    } catch { return false; }
  }
  async function shareLocation() {
    try { await Share.share({message:`${source === 'gps' ? 'My GPS location' : 'Training location (not a fresh GPS reading)'}: ${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}`}); }
    catch { setNotice({title:'Sharing unavailable',body:'You can read the coordinates from the SOS screen.',tone:'info'}); }
  }
  return {area,position,source,phase,setPhase,selected,selectedId,options,accessible,setAccessible,schematic,setSchematic,gpsBusy,ready,storage,connection,notice,setNotice,outside,backend,token,revision,mutate,locate,manual,find,select,preview,navigate,stop,changeDisaster,blockAhead,demoStep,save,login,publish,shareLocation,guidance:routeGuidance(area,selected?.route||null)};
}
export type EvacuationModel = ReturnType<typeof useEvacuation>;
