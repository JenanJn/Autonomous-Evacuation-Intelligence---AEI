/**
 * SimulatedBanner — persistent top banner shown on every screen that
 * uses simulated/demo data.
 *
 * Requirements:
 * - Must be visible at all times when is_simulated=true.
 * - Must never be hidden or dismissed by the user in demo mode.
 * - Text must be unambiguous: "SIMULATED DATA", not just "Demo".
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors } from '../theme/colors';

interface Props {
  visible: boolean;
}

export function SimulatedBanner({ visible }: Props) {
  if (!visible) return null;
  return (
    <View style={styles.container} accessibilityRole="alert">
      <Text style={styles.text} accessibilityLabel="Warning: This screen shows simulated data">
        ⚠ SIMULATED DATA — Not a real emergency scenario. Do not use for actual evacuation decisions.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.simulatedBg,
    borderBottomWidth: 2,
    borderBottomColor: Colors.simulated,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  text: {
    color: Colors.simulated,
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
    letterSpacing: 0.3,
  },
});
