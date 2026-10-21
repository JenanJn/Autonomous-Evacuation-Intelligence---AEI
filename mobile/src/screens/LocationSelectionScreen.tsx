import React, { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import * as Location from 'expo-location';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import type { RootStackParamList } from '../navigation/types';
import { useEvacuation } from '../evacuation/useEvacuation';
import { emptyArea } from '../evacuation/network';
import { EvacuationMap } from '../evacuation/ui/EvacuationMap';
import type { MapHandle } from '../evacuation/ui/mapTypes';
import type { Point } from '../evacuation/engine';
import { Action, C } from '../evacuation/ui/primitives';
export function LocationSelectionScreen(){const nav=useNavigation<NativeStackNavigationProp<RootStackParamList>>(),route=useRoute<RouteProp<RootStackParamList,'LocationSelection'>>(),m=useEvacuation(),map=useRef<MapHandle>(null);
 const [pin,setPin]=useState<Point|null>(m.prepared?m.position:null),[lat,setLat]=useState(''),[lon,setLon]=useState(''),[gps,setGps]=useState(false),[error,setError]=useState('');
 const point=pin||{lat:0,lon:0};const area=m.prepared?m.area:emptyArea(point);
 function choose(p:Point){setPin(p);setLat(p.lat.toFixed(6));setLon(p.lon.toFixed(6));setError('');}
 async function locate(){setGps(true);try{if((await Location.requestForegroundPermissionsAsync()).status!=='granted')throw Error('Location permission is off. Drop a pin or enter coordinates.');const r=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.Balanced});const p={lat:r.coords.latitude,lon:r.coords.longitude};choose(p);map.current?.focus(p);}catch(e){setError(e instanceof Error?e.message:'GPS unavailable');}finally{setGps(false);}}
 function coordinates(){const p={lat:Number(lat),lon:Number(lon)};if(!lat.trim()||!lon.trim()||!Number.isFinite(p.lat)||!Number.isFinite(p.lon)||Math.abs(p.lat)>85||Math.abs(p.lon)>180){setError('Enter latitude −85 to 85 and longitude −180 to 180.');return;}choose(p);map.current?.focus(p);}
 async function confirm(){if(pin&&await m.prepare(pin,route.params?.disaster||'Flood','manual'))nav.navigate('EvacuationMap');}
 return <View style={{flex:1,backgroundColor:C.canvas}}><View style={s.map}><EvacuationMap ref={map} area={area} position={point} positionLabel="Selected starting point" selectedId={null} route={null} schematic={m.connection==='offline'} bottomSpace={0} onShelter={()=>{}} onHazard={()=>{}} onManual={choose} navigating={false} focusRoute={false} compact picking worldView={!pin}/><View pointerEvents="none" style={s.hint}><Text style={s.hintText}>{pin?'Tap the map to move your starting point':'Zoom in anywhere and tap to drop a pin'}</Text></View><Pressable accessibilityRole="button" onPress={()=>void locate()} style={s.gps}>{gps?<ActivityIndicator color={C.green}/>:<Text style={{fontWeight:'800',color:C.green}}>◎ Locate me</Text>}</Pressable></View>
 <View style={s.panel}><Text style={s.title}>Choose your starting location</Text><Text style={s.small}>{pin?`${pin.lat.toFixed(6)}, ${pin.lon.toFixed(6)}`:'No location selected. GPS and manual coordinates are also available.'}</Text><View style={s.row}><TextInput accessibilityLabel="Latitude" placeholder="Latitude" style={s.input} value={lat} onChangeText={setLat} keyboardType="numbers-and-punctuation"/><TextInput accessibilityLabel="Longitude" placeholder="Longitude" style={s.input} value={lon} onChangeText={setLon} keyboardType="numbers-and-punctuation"/><Pressable accessibilityRole="button" onPress={coordinates} style={s.go}><Text style={{fontWeight:'800',color:C.green}}>Go</Text></Pressable></View>
 {(error||m.notice?.tone==='danger')&&<Text accessibilityLiveRegion="polite" style={s.error}>{error||m.notice?.body}</Text>}
 <Action label={m.loading?'Downloading nearby streets…':'Prepare This Location'} busy={m.loading} disabled={!pin} icon="arrow-forward" onPress={()=>void confirm()}/>{m.loading&&<Action label="Cancel Download" tone="quiet" onPress={m.cancelDownload}/>}<Text style={[s.small,{marginTop:9}]}>No city restriction. New areas require internet; the road service may be unavailable or have incomplete coverage.</Text></View></View>;
}
const s=StyleSheet.create({map:{flex:1,minHeight:180},hint:{position:'absolute',top:12,left:15,right:15,padding:12,borderRadius:12,backgroundColor:'#ffffffed'},hintText:{fontSize:13,fontWeight:'700',color:C.ink,textAlign:'center'},gps:{position:'absolute',bottom:35,right:14,backgroundColor:'white',padding:14,borderRadius:24,borderWidth:1,borderColor:'#d6e1da'},panel:{padding:20,paddingBottom:27,backgroundColor:'white',gap:10},title:{fontSize:20,fontWeight:'800',color:C.ink},small:{fontSize:12,lineHeight:18,color:C.muted},row:{flexDirection:'row',gap:8},input:{flex:1,minWidth:0,padding:12,borderRadius:10,backgroundColor:'#f3f6f3',fontSize:14,color:C.ink},go:{justifyContent:'center',padding:12},error:{color:C.red,fontSize:13,lineHeight:19}});
