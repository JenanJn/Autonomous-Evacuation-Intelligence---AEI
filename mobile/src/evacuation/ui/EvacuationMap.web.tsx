import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { MAP_DOCUMENT, mapSnapshot } from './mapDocument';
import type { MapHandle, MapProps } from './mapTypes';
import type { Point } from '../engine';

/** Browser QA uses exactly the bundled document used by the native WebView. */
export const EvacuationMap=forwardRef<MapHandle,MapProps>(function EvacuationMap(props,ref){
 const frame=useRef<HTMLIFrameElement>(null),latest=useRef(props),ready=useRef(false);
 latest.current=props;
 function send(type:string,point?:Point){if(ready.current)frame.current?.contentWindow?.postMessage({aeiCommand:true,type,payload:type==='update'?mapSnapshot(latest.current):undefined,point},'*');}
 useImperativeHandle(ref,()=>({focus:(point)=>send('focus',point),overview:()=>send('overview')}),[]);
 useEffect(()=>{send('update');},[props]);
 useEffect(()=>{
  function receive(e:MessageEvent){if(e.source!==frame.current?.contentWindow||!e.data?.aeiMap)return;const m=e.data;
   if(m.type==='ready'){ready.current=true;send('update');}
   else if(m.type==='shelter'&&latest.current.area.shelters.some(s=>s.id===m.id))latest.current.onShelter(m.id);
   else if(m.type==='hazard')latest.current.onHazard();
   else if(m.type==='pan')latest.current.onPan?.();
   else if(m.type==='manual'&&!latest.current.navigating&&Number.isFinite(m.point?.lat)&&Number.isFinite(m.point?.lon))latest.current.onManual(m.point);
   else if(m.type==='license')window.open('https://www.openstreetmap.org/copyright','_blank','noopener,noreferrer');
  }
  window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
 },[]);
 return <iframe ref={frame} srcDoc={MAP_DOCUMENT} sandbox="allow-scripts" onLoad={()=>{ready.current=true;send('update');}} title="OpenStreetMap evacuation map" style={{position:'absolute',inset:0,width:'100%',height:'100%',border:0,background:'#e6eee8'}}/>;
});
