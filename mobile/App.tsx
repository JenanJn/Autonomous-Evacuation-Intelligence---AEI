/**
 * AEI — Autonomous Evacuation Intelligence
 * Mobile application root component.
 *
 * ╔══════════════════════════════════════════════════════════════╗
 * ║  RESEARCH PROTOTYPE — ALL DATA IS SYNTHETIC                 ║
 * ║  Do not use for real emergency decisions.                   ║
 * ╚══════════════════════════════════════════════════════════════╝
 */
import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppNavigator } from './src/navigation/AppNavigator';

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" backgroundColor="#ffffff" />
      <AppNavigator />
    </SafeAreaProvider>
  );
}
