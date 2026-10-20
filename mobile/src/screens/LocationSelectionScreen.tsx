/**
 * LocationSelectionScreen
 *
 * Allows the user to manually enter or select a location.
 * Full interactive map support requires expo-maps or react-native-maps
 * (not yet installed). This screen provides a coordinate-entry fallback
 * and a clear stub for the map picker.
 *
 * We never silently substitute synthetic coordinates for the user's
 * intended location.
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { Colors } from '../theme/colors';
import { WarningCard } from '../components/WarningCard';
import type { RootStackParamList } from '../navigation/types';
import type { UserLocation } from '../types/api';

type Nav = NativeStackNavigationProp<RootStackParamList, 'LocationSelection'>;

export function LocationSelectionScreen() {
  const navigation = useNavigation<Nav>();
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [label, setLabel] = useState('');

  function handleConfirm() {
    const parsedLat = parseFloat(lat);
    const parsedLon = parseFloat(lon);

    if (isNaN(parsedLat) || isNaN(parsedLon)) {
      Alert.alert('Invalid coordinates', 'Please enter valid decimal latitude and longitude.');
      return;
    }
    if (parsedLat < -90 || parsedLat > 90) {
      Alert.alert('Invalid latitude', 'Latitude must be between -90 and 90.');
      return;
    }
    if (parsedLon < -180 || parsedLon > 180) {
      Alert.alert('Invalid longitude', 'Longitude must be between -180 and 180.');
      return;
    }

    const location: UserLocation = {
      mode: 'map',
      lat: parsedLat,
      lon: parsedLon,
      node_id: '',   // resolved by backend
      label: label.trim() || `(${parsedLat.toFixed(4)}, ${parsedLon.toFixed(4)})`,
    };

    navigation.navigate('EvacuationPlan', { location, demoMode: false });
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.scroll}>
          <Text style={styles.heading}>Choose Starting Location</Text>

          <WarningCard
            warnings={[
              'Requires a connected backend to resolve coordinates to a road-network node.',
              'Use Demo Mode on the Home screen to test without a backend.',
            ]}
            severity="info"
          />

          {/* Map picker stub */}
          <View style={styles.mapStub}>
            <Text style={styles.mapStubIcon}>🗺️</Text>
            <Text style={styles.mapStubTitle}>Interactive Map Picker</Text>
            <Text style={styles.mapStubDesc}>
              Full map interaction requires expo-maps or react-native-maps.{'\n'}
              This feature is planned for the next iteration.{'\n'}
              Use the coordinate entry below as a fallback.
            </Text>
          </View>

          {/* Manual coordinate entry */}
          <View style={styles.formSection}>
            <Text style={styles.formTitle}>Enter Coordinates Manually</Text>

            <Text style={styles.inputLabel}>Latitude</Text>
            <TextInput
              style={styles.input}
              value={lat}
              onChangeText={setLat}
              placeholder="e.g. 13.0827"
              placeholderTextColor={Colors.textMuted}
              keyboardType="decimal-pad"
              returnKeyType="next"
              accessibilityLabel="Latitude input"
            />

            <Text style={styles.inputLabel}>Longitude</Text>
            <TextInput
              style={styles.input}
              value={lon}
              onChangeText={setLon}
              placeholder="e.g. 80.2707"
              placeholderTextColor={Colors.textMuted}
              keyboardType="decimal-pad"
              returnKeyType="next"
              accessibilityLabel="Longitude input"
            />

            <Text style={styles.inputLabel}>Label (optional)</Text>
            <TextInput
              style={styles.input}
              value={label}
              onChangeText={setLabel}
              placeholder="e.g. My neighbourhood"
              placeholderTextColor={Colors.textMuted}
              returnKeyType="done"
              accessibilityLabel="Location label input"
            />

            <TouchableOpacity
              style={styles.confirmButton}
              onPress={handleConfirm}
              accessibilityRole="button"
              accessibilityLabel="Confirm this location"
            >
              <Text style={styles.confirmButtonText}>Confirm Location →</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { padding: 20, paddingBottom: 40 },

  heading: {
    fontSize: 22,
    fontWeight: '800',
    color: Colors.textPrimary,
    marginBottom: 16,
  },

  mapStub: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    borderStyle: 'dashed',
    alignItems: 'center',
    padding: 32,
    marginVertical: 16,
  },
  mapStubIcon: { fontSize: 48, marginBottom: 8 },
  mapStubTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.textSecondary,
    marginBottom: 8,
  },
  mapStubDesc: {
    fontSize: 12,
    color: Colors.textMuted,
    textAlign: 'center',
    lineHeight: 18,
  },

  formSection: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  formTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: Colors.textPrimary,
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: 4,
  },
  input: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    color: Colors.textPrimary,
    backgroundColor: Colors.background,
    marginBottom: 16,
  },
  confirmButton: {
    backgroundColor: Colors.primary,
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
    marginTop: 4,
  },
  confirmButtonText: {
    color: Colors.textOnDark,
    fontSize: 15,
    fontWeight: '700',
  },
});
