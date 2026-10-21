import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import MapView, { Circle, Marker, Polyline } from 'react-native-maps';
import { disasterVisual, hazardTexturePoints } from '../presentation';
import { MapHandle, MapProps } from './mapTypes';
import { C } from './primitives';
const coordinate=(p:{lat:number;lon:number})=>({latitude:p.lat,longitude:p.lon});
const mapStyle=[{featureType:'poi',stylers:[{visibility:'off'}]},{featureType:'transit',stylers:[{visibility:'off'}]},{featureType:'landscape',elementType:'geometry',stylers:[{color:'#edf1e8'}]},{featureType:'road',elementType:'geometry',stylers:[{color:'#ffffff'}]},{featureType:'water',elementType:'geometry',stylers:[{color:'#cedfe7'}]}];
export const EvacuationMap=forwardRef<MapHandle,MapProps>(function EvacuationMap(props,ref){
 const map=useRef<MapView>(null),ready=useRef(false);
 const propsRef=useRef(props);propsRef.current=props;
 function overview(){const p=propsRef.current;map.current?.fitToCoordinates([p.position,...p.area.shelters,...p.area.hazards.filter(h=>h.active).map(h=>({...h,lat:h.lat+h.radius/111320}))].map(coordinate),{edgePadding:{top:175,left:88,right:88,bottom:p.bottomSpace+25},animated:true});}
 function focus(point=propsRef.current.position){map.current?.animateToRegion({...coordinate(point),latitudeDelta:.018,longitudeDelta:.018},450);}
 useImperativeHandle(ref,()=>({focus,overview}));
 useEffect(()=>{if(ready.current)overview();},[props.area.origin.lat,props.area.origin.lon]);
 const signature=props.route?.path.join('|')||'';
 useEffect(()=>{
  if(!ready.current)return; if(!props.focusRoute||!props.route){overview();return;}
  map.current?.fitToCoordinates([props.position,...props.area.hazards.filter(h=>h.active).map(h=>({...h,lat:h.lat+h.radius/111320})),...props.route.path.map(id=>props.area.nodes.find(n=>n.id===id)!)].map(coordinate),{edgePadding:{top:props.navigating?210:175,left:88,right:88,bottom:props.bottomSpace+24},animated:true});
 },[props.selectedId,signature,props.navigating,props.bottomSpace,props.focusRoute]);
 return <MapView ref={map} style={StyleSheet.absoluteFillObject} initialRegion={{...coordinate(props.position),latitudeDelta:.025,longitudeDelta:.021}} customMapStyle={mapStyle} mapType={props.schematic?'none':'standard'} showsCompass={false} toolbarEnabled={false} showsMyLocationButton={false} rotateEnabled={false} onMapReady={()=>{ready.current=true;overview();}} onPanDrag={props.onPan} onLongPress={e=>{if(!props.navigating)props.onManual({lat:e.nativeEvent.coordinate.latitude,lon:e.nativeEvent.coordinate.longitude});}}>
 {props.area.roads.map(road=><Polyline key={road.id} coordinates={[coordinate(props.area.nodes.find(n=>n.id===road.u)!),coordinate(props.area.nodes.find(n=>n.id===road.v)!)]} strokeColor={road.status==='BLOCKED'?'#c33b30':props.schematic?'#9cafaa':'#8aa59c80'} strokeWidth={road.status==='BLOCKED'?5:2} lineDashPattern={road.status==='BLOCKED'?[7,6]:undefined} zIndex={road.status==='BLOCKED'?7:1}/>)}
 {props.area.hazards.filter(h=>h.active).map(h=>{const v=disasterVisual(h.type);return <React.Fragment key={h.id}>
 <Circle center={coordinate(h)} radius={h.radius+20} fillColor="transparent" strokeColor={v.color+'60'} strokeWidth={1} zIndex={2}/>
 <Circle center={coordinate(h)} radius={h.radius} fillColor={v.fill} strokeColor={v.color} strokeWidth={2} zIndex={3}/>
 {hazardTexturePoints(h).map((point,index)=><Marker key={index} coordinate={coordinate(point)} anchor={{x:.5,y:.5}} tappable={false} zIndex={4}><Text style={[s.texture,{color:v.color,fontSize:h.type==='Flood'?34:23}]}>{v.texture}</Text></Marker>)}
 <Marker coordinate={coordinate({...h,lat:h.lat+h.radius/111320})} anchor={{x:.5,y:1}} zIndex={5} onPress={props.onHazard} accessibilityLabel={v.zone}><View style={[s.hazardLabel,{backgroundColor:v.background,borderColor:v.color}]}><Text style={s.hazardIcon}>{v.icon}</Text><Text style={[s.hazardText,{color:v.color}]}>{v.zone}</Text></View></Marker>
 </React.Fragment>;})}
 {props.route&&<Polyline coordinates={props.route.path.map(id=>coordinate(props.area.nodes.find(n=>n.id===id)!))} strokeColor="#ffffff" strokeWidth={11} zIndex={8}/>}
 {props.route&&<Polyline coordinates={props.route.path.map(id=>coordinate(props.area.nodes.find(n=>n.id===id)!))} strokeColor={C.green} strokeWidth={6} zIndex={9}/>}
 {props.area.roads.filter(r=>r.status==='BLOCKED').map(r=>{const a=props.area.nodes.find(n=>n.id===r.u)!,b=props.area.nodes.find(n=>n.id===r.v)!;return <Marker key={'block'+r.id} coordinate={{latitude:(a.lat+b.lat)/2,longitude:(a.lon+b.lon)/2}} zIndex={10} anchor={{x:.5,y:.5}} title="Road closed"><View style={s.block}><Text style={s.blockText}>×</Text></View></Marker>;})}
 {props.area.facilities.map(f=><Marker key={f.name} coordinate={coordinate(f)} title={f.name+' · simulated'} zIndex={5}><View style={s.medical}><Text style={s.medicalText}>+</Text></View></Marker>)}
 {props.area.shelters.map((shelter,i)=>{const selected=props.selectedId===shelter.id,open=shelter.status==='OPEN'&&shelter.available>0;return <Marker key={shelter.id} coordinate={coordinate(shelter)} zIndex={selected?14:12} anchor={{x:.5,y:.5}} onPress={()=>props.onShelter(shelter.id)}><View style={s.shelterMarker}><View style={[s.shelterPin,{backgroundColor:open?selected?C.green:'white':'#fcecea',borderColor:open?C.green:'#c33b30'}]}><Text style={[s.shelterNumber,{color:selected&&open?'white':open?C.green:'#b3342d'}]}>⌂ {i+1}</Text></View>{!props.compact&&<Text style={s.mapLabel}>{shelter.name}</Text>}</View></Marker>;})}
 <Marker coordinate={coordinate(props.position)} title={props.positionLabel} zIndex={20} anchor={{x:.5,y:.5}}><View style={s.youHalo}><View style={s.youDot}/></View></Marker>
 </MapView>;
});
const s=StyleSheet.create({texture:{fontWeight:'800'},hazardLabel:{borderWidth:1,borderRadius:9,paddingHorizontal:9,paddingVertical:6,flexDirection:'row',alignItems:'center',gap:5},hazardIcon:{fontSize:21},hazardText:{fontSize:10,fontWeight:'900',letterSpacing:.5},block:{width:26,height:26,borderRadius:13,backgroundColor:'#bc3026',borderWidth:2,borderColor:'white',alignItems:'center',justifyContent:'center'},blockText:{fontSize:24,color:'white',lineHeight:25,fontWeight:'900'},medical:{backgroundColor:'white',width:28,height:28,borderRadius:8,borderWidth:1,borderColor:'#b7caca',alignItems:'center',justifyContent:'center'},medicalText:{color:'#628d9d',fontSize:25,fontWeight:'800',lineHeight:26},shelterMarker:{alignItems:'center',padding:3},shelterPin:{borderWidth:2,borderRadius:14,minWidth:48,height:38,alignItems:'center',justifyContent:'center',paddingHorizontal:8},shelterNumber:{fontSize:19,fontWeight:'800'},mapLabel:{fontSize:10,fontWeight:'700',color:'#25473d',backgroundColor:'#ffffffed',padding:3,borderRadius:3,marginTop:2,maxWidth:170},youHalo:{width:38,height:38,borderRadius:19,backgroundColor:'#227de633',alignItems:'center',justifyContent:'center'},youDot:{width:18,height:18,borderRadius:9,backgroundColor:'#237ce0',borderWidth:3,borderColor:'white'}});
