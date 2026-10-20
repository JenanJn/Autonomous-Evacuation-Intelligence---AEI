/**
 * ConnectivityBadge — small inline indicator of backend connection status.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors } from '../theme/colors';
import type { ConnectivityStatus } from '../types/api';

interface Props {
  status: ConnectivityStatus;
}

const CONFIG: Record<ConnectivityStatus, { dot: string; label: string }> = {
  connected:    { dot: Colors.success, label: 'Live' },
  disconnected: { dot: Colors.riskUnknown, label: 'Offline' },
  unknown:      { dot: Colors.warning, label: 'Checking…' },
};

export function ConnectivityBadge({ status }: Props) {
  const { dot, label } = CONFIG[status];
  return (
    <View style={styles.container}>
      <View style={[styles.dot, { backgroundColor: dot }]} />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  label: { fontSize: 12, color: Colors.textSecondary },
});
