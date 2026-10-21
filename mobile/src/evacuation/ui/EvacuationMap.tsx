import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { MAP_BASE_URL, MAP_DOCUMENT, mapSnapshot } from './mapDocument';
import type { MapHandle, MapProps } from './mapTypes';
import type { Point } from '../engine';

const SOURCE = { html: MAP_DOCUMENT, baseUrl: MAP_BASE_URL };
export const EvacuationMap = forwardRef<MapHandle, MapProps>(function EvacuationMap(props, ref) {
  const view = useRef<WebView>(null), ready = useRef(false), latest = useRef(props);
  const sentArea=useRef<MapProps['area']|null>(null);
  const pending = useRef<{type:'overview'|'focus';point?:Point} | null>(null);
  const [error, setError] = useState(false), [generation, setGeneration] = useState(0);
  latest.current = props;
  function send(type: 'update'|'overview'|'focus', point?: Point) {
    if (!ready.current) { if(type!=='update')pending.current={type,point}; return; }
    const snapshot=type==='update'?mapSnapshot(latest.current):null;
    const key=snapshot?.area||null;
    const argument=JSON.stringify(snapshot?{...snapshot,area:key===sentArea.current?undefined:snapshot.area}:point??null).replace(/</g,'\\u003c').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
    if(snapshot)sentArea.current=key;
    view.current?.injectJavaScript(`window.AEIMap && window.AEIMap.${type}(${argument}); true;`);
  }
  useImperativeHandle(ref, () => ({ overview:()=>send('overview'), focus:(point)=>send('focus',point) }), []);
  useEffect(() => { send('update'); }, [props]);
  function message(event: WebViewMessageEvent) {
    try {
      const m=JSON.parse(event.nativeEvent.data);
      if(m.type==='ready') { sentArea.current=null;ready.current=true;send('update');const command=pending.current;pending.current=null;if(command)send(command.type,command.point); }
      else if(m.type==='shelter'&&latest.current.area.shelters.some(s=>s.id===m.id)) latest.current.onShelter(m.id);
      else if(m.type==='hazard')latest.current.onHazard();
      else if(m.type==='pan')latest.current.onPan?.();
      else if(m.type==='manual'&&!latest.current.navigating&&Number.isFinite(m.point?.lat)&&Number.isFinite(m.point?.lon)&&Math.abs(m.point.lat)<=85&&Math.abs(m.point.lon)<=180)latest.current.onManual(m.point);
      else if(m.type==='license')void Linking.openURL('https://www.openstreetmap.org/copyright');
    } catch { /* Ignore malformed bridge messages. */ }
  }
  function retry(){sentArea.current=null;ready.current=false;setError(false);setGeneration(n=>n+1);}
  return <View style={StyleSheet.absoluteFill}>
    <WebView key={generation} ref={view} source={SOURCE} style={s.map}
      originWhitelist={['*']} onMessage={message} javaScriptEnabled domStorageEnabled={false}
      cacheEnabled scrollEnabled={false} bounces={false} overScrollMode="never"
      applicationNameForUserAgent={`AEI-Evacuation/0.3 (+${MAP_BASE_URL})`}
      allowFileAccess={false} allowFileAccessFromFileURLs={false} allowUniversalAccessFromFileURLs={false}
      mixedContentMode="never" thirdPartyCookiesEnabled={false} sharedCookiesEnabled={false}
      setSupportMultipleWindows={false}
      onShouldStartLoadWithRequest={r=>r.url==='about:blank'||r.url===MAP_BASE_URL}
      onLoadStart={()=>{ready.current=false;}}
      onError={()=>setError(true)} onContentProcessDidTerminate={retry} onRenderProcessGone={()=>setError(true)}/>
    {error&&<View style={[s.failure,{bottom:props.bottomSpace+70}]}><Text style={s.title}>Map could not start</Text><Text style={s.body}>Your saved route data is retained. Reload the map to continue.</Text><Pressable accessibilityRole="button" onPress={retry} style={s.retry}><Text style={s.retryText}>Reload map</Text></Pressable></View>}
  </View>;
});
const s=StyleSheet.create({map:{flex:1,backgroundColor:'#e6eee8'},failure:{position:'absolute',left:20,right:20,padding:18,borderRadius:14,backgroundColor:'white'},title:{fontSize:18,fontWeight:'800',color:'#183b2f'},body:{fontSize:14,lineHeight:20,color:'#53685e',marginTop:6},retry:{backgroundColor:'#087457',borderRadius:10,padding:14,marginTop:12,alignItems:'center'},retryText:{color:'white',fontWeight:'700'}});
