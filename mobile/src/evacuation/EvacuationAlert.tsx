import React from 'react';
import {Modal,Text} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useEvacuation} from './useEvacuation';
import {Action} from './ui/primitives';
export function EvacuationAlert(){const m=useEvacuation();return <Modal visible={!!m.warning} animationType="fade" onRequestClose={m.dismissWarning}><SafeAreaView style={{flex:1,backgroundColor:'#8e251f',justifyContent:'center',padding:28}}><Text style={{fontSize:12,fontWeight:'800',letterSpacing:2,color:'#ffd9d2'}}>SIMULATED EMERGENCY ALERT</Text><Text style={{fontSize:35,lineHeight:42,fontWeight:'800',color:'white',marginTop:22}}>Review your surroundings.</Text><Text style={{fontSize:18,lineHeight:28,color:'white',marginTop:22,marginBottom:30}}>{m.warning}</Text><Action label="Acknowledge and silence alert" tone="secondary" onPress={m.dismissWarning}/><Text style={{fontSize:12,color:'#ffd9d2',marginTop:22}}>Training only. No official emergency alert or SMS has been sent.</Text></SafeAreaView></Modal>;}
