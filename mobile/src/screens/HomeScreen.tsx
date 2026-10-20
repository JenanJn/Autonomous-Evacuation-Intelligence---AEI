/**
 * HomeScreen
 *
 * Entry point for the app. Shows three starting-location options:
 *   1. Use My Current Location (GPS)
 *   2. Choose on Map
 *   3. Demo Mode (deterministic synthetic data, clearly labelled)
 *
 * Requirements enforced here:
 * - GPS option shows permission status before attempting to read location.
 * - Demo Mode is labelled SIMULATED in the button text AND in a disclaimer.
 * - We never silently substitute synthetic coordinates for real GPS.
 * - Connectivity status is shown in the header.
 */
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as Location from 'expo-location';

import { Colors } from '../theme/colors';
import { ConnectivityBadge } from '../components/ConnectivityBadge';
import { getConnectivityStatus } from '../services/apiClient';
import type { RootStackParamList } from '../navigation/types';
import type { ConnectivityStatus, UserLocation } from '../types/api';

type Nav = NativeStackNavigationProp<RootStackParamList, 'Home'>;

export function HomeScreen() {
  const navigation = useNavigation<Nav>();
  const [connectivity, setConnectivity] = useState<ConnectivityStatus>('unknown');
  const [gpsLoading, setGpsLoading] = useState(false);

  // Check backend connectivity once on mount.
  useEffect(() => {
    let cancelled = false;
    getConnectivityStatus().then((s) => {
      if (!cancelled) setConnectivity(s);
    });
    return () => { cancelled = true; };
  }, []);

  // ── Option 1: GPS ─────────────────────────────────────────────────────────
  async function handleGPS() {
    setGpsLoading(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();

      if (status !== 'granted') {
        Alert.alert(
          'Location Permission Denied',
          'AEI needs location access to calculate an evacuation route from your '
          + 'current position.\n\nYou can still use Demo Mode or choose a location on the map.',
          [{ text: 'OK' }],
        );
        return;
      }

      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      // Pass real coordinates — never substitute synthetic ones.
      const location: UserLocation = {
        mode: 'gps',
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        // node_id will be resolved by the backend; empty string signals "not yet snapped".
        node_id: '',
        label: `GPS (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`,
      };

      navigation.navigate('EvacuationPlan', { location, demoMode: true });
    } catch (err) {
      Alert.alert(
        'Location Error',
        'Could not read GPS position. Please try again or use Demo Mode.',
        [{ text: 'OK' }],
      );
    } finally {
      setGpsLoading(false);
    }
  }

  // ── Option 2: Map picker ──────────────────────────────────────────────────
  function handleMap() {
    navigation.navigate('LocationSelection');
  }

  // ── Option 3: Demo Mode ───────────────────────────────────────────────────
  function handleDemo() {
    const location: UserLocation = {
      mode: 'demo',
      lat: 0.0,
      lon: 0.0,
      node_id: 'A',
      label: 'Demo Origin Node A [SIMULATED]',
    };
    navigation.navigate('EvacuationPlan', { location, demoMode: true });
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.scroll} bounces={false}>
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerTop}>
            <Text style={styles.appName}>AEI</Text>
            <ConnectivityBadge status={connectivity} />
          </View>
          <Text style={styles.tagline}>Autonomous Evacuation Intelligence</Text>
          <Text style={styles.subtitle}>
            Decision-support tool — synthetic prototype
          </Text>
        </View>

        {/* Emergency status bar */}
        <View style={styles.alertBanner}>
          <Text style={styles.alertText}>
            ⚠  This app uses SIMULATED data. Do not use for real emergencies.
          </Text>
        </View>

        {/* Location selection */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Choose your starting location</Text>

          {/* Option 1 — GPS */}
          <TouchableOpacity
            style={[styles.optionCard, styles.optionGPS]}
            onPress={handleGPS}
            disabled={gpsLoading}
            accessibilityLabel="Use my current GPS location"
            accessibilityRole="button"
          >
            <View style={styles.optionIcon}>
              <Text style={styles.optionIconText}>📍</Text>
            </View>
            <View style={styles.optionContent}>
              <Text style={styles.optionTitle}>Demo at My Current Location</Text>
              <Text style={styles.optionDesc}>
                Reads GPS and places a labeled simulated disaster nearby.
              </Text>
              {Platform.OS !== 'web' && (
                <Text style={styles.optionNote}>
                  Training data works without a backend.
                </Text>
              )}
            </View>
            {gpsLoading && (
              <ActivityIndicator color={Colors.primary} style={{ marginLeft: 8 }} />
            )}
          </TouchableOpacity>

          {/* Option 2 — Map */}
          <TouchableOpacity
            style={[styles.optionCard, styles.optionMap]}
            onPress={handleMap}
            accessibilityLabel="Choose location on map"
            accessibilityRole="button"
          >
            <View style={styles.optionIcon}>
              <Text style={styles.optionIconText}>🗺️</Text>
            </View>
            <View style={styles.optionContent}>
              <Text style={styles.optionTitle}>Choose on Map</Text>
              <Text style={styles.optionDesc}>
                Tap a point on the map to set your evacuation start.
              </Text>
            </View>
          </TouchableOpacity>

          {/* Option 3 — Demo */}
          <TouchableOpacity
            style={[styles.optionCard, styles.optionDemo]}
            onPress={handleDemo}
            accessibilityLabel="Start Demo Mode with simulated data"
            accessibilityRole="button"
          >
            <View style={styles.optionIcon}>
              <Text style={styles.optionIconText}>🧪</Text>
            </View>
            <View style={styles.optionContent}>
              <Text style={[styles.optionTitle, { color: Colors.simulated }]}>
                Demo Mode  [SIMULATED]
              </Text>
              <Text style={styles.optionDesc}>
                Uses deterministic synthetic data. Works offline.
                No GPS or backend required.
              </Text>
              <Text style={[styles.optionNote, { color: Colors.simulated }]}>
                Data is synthetic — not real observations.
              </Text>
            </View>
          </TouchableOpacity>
        </View>

        {/* Quick links */}
        <View style={styles.quickLinks}>
          <TouchableOpacity
            onPress={() => navigation.navigate('EmergencyGuide')}
            style={styles.quickLink}
            accessibilityRole="button"
          >
            <Text style={styles.quickLinkText}>📋 Emergency Safety Guide</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => navigation.navigate('Settings')}
            style={styles.quickLink}
            accessibilityRole="button"
          >
            <Text style={styles.quickLinkText}>⚙️ Settings</Text>
          </TouchableOpacity>
        </View>

        {/* Disclaimer */}
        <View style={styles.disclaimer}>
          <Text style={styles.disclaimerText}>
            AEI is a research prototype. Risk scores are UNCALIBRATED
            decision-support proxies — not calibrated flood probabilities.
            Routes are not guaranteed safe. Shelter data is synthetic.
          </Text>
          <Text style={styles.disclaimerText}>
            Contract version 0.1.0 · Model: RandomForest v0.1.0 (synthetic)
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { paddingBottom: 32 },

  header: {
    backgroundColor: Colors.primary,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 24,
  },
  headerTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  appName: {
    fontSize: 32,
    fontWeight: '900',
    color: Colors.textOnDark,
    letterSpacing: 4,
  },
  tagline: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.textOnDark,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.7)',
  },

  alertBanner: {
    backgroundColor: '#fff3cd',
    borderBottomWidth: 1,
    borderBottomColor: '#ffc107',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  alertText: {
    fontSize: 12,
    color: '#856404',
    fontWeight: '600',
    textAlign: 'center',
  },

  section: { paddingHorizontal: 16, paddingTop: 20 },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: 12,
  },

  optionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    backgroundColor: Colors.surface,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  optionGPS:  { borderColor: Colors.primary },
  optionMap:  { borderColor: Colors.primaryLight },
  optionDemo: { borderColor: Colors.simulated },

  optionIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: Colors.surfaceElevated,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  optionIconText: { fontSize: 22 },
  optionContent: { flex: 1 },
  optionTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: 3,
  },
  optionDesc: { fontSize: 12, color: Colors.textSecondary, lineHeight: 17 },
  optionNote: { fontSize: 11, color: Colors.textMuted, marginTop: 3, fontStyle: 'italic' },

  quickLinks: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 16,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 16,
  },
  quickLink: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: Colors.surfaceElevated,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  quickLinkText: { fontSize: 13, color: Colors.primary, fontWeight: '600' },

  disclaimer: {
    marginHorizontal: 16,
    padding: 12,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  disclaimerText: {
    fontSize: 10,
    color: Colors.textMuted,
    lineHeight: 15,
    textAlign: 'center',
    marginBottom: 2,
  },
});
