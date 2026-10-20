/**
 * WarningCard — displays a list of warnings prominently.
 * Used on every screen that shows risk or route data.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors } from '../theme/colors';

interface Props {
  warnings: string[];
  /** 'warning' = orange, 'error' = red, 'info' = blue */
  severity?: 'warning' | 'error' | 'info';
}

const SEVERITY_COLORS = {
  warning: { border: Colors.warning, bg: '#fff8e1', text: '#5d4037', icon: '⚠' },
  error:   { border: Colors.error,   bg: '#ffebee', text: '#b71c1c', icon: '✕' },
  info:    { border: Colors.info,    bg: '#e3f2fd', text: '#01579b', icon: 'ℹ' },
};

export function WarningCard({ warnings, severity = 'warning' }: Props) {
  if (warnings.length === 0) return null;
  const c = SEVERITY_COLORS[severity];
  return (
    <View style={[styles.card, { borderLeftColor: c.border, backgroundColor: c.bg }]}
          accessibilityRole="alert">
      {warnings.map((w, i) => (
        <View key={i} style={styles.row}>
          <Text style={[styles.icon, { color: c.border }]}>{c.icon}</Text>
          <Text style={[styles.text, { color: c.text }]}>{w}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderLeftWidth: 4,
    borderRadius: 6,
    padding: 12,
    marginVertical: 8,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 4,
  },
  icon: {
    fontSize: 13,
    marginRight: 6,
    marginTop: 1,
  },
  text: {
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
  },
});
