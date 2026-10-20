/**
 * SettingsScreen
 *
 * Connectivity status, backend URL display, and app metadata.
 * No editable settings are stored to disk in this iteration.
 */
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors } from '../theme/colors';
import { ConnectivityBadge } from '../components/ConnectivityBadge';
import { checkHealth } from '../services/apiClient';
import type { ApiHealth, ConnectivityStatus } from '../types/api';

export function SettingsScreen() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [connectivity, setConnectivity] = useState<ConnectivityStatus>('unknown');
  const [checking, setChecking] = useState(false);

  async function runCheck() {
    setChecking(true);
    setConnectivity('unknown');
    const h = await checkHealth();
    setHealth(h);
    setConnectivity(h.status === 'ok' ? 'connected' : 'disconnected');
    setChecking(false);
  }

  useEffect(() => { runCheck(); }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.heading}>Settings</Text>

        {/* Connectivity card */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Backend Connectivity</Text>
            <ConnectivityBadge status={connectivity} />
          </View>

          <InfoRow label="Backend URL" value={health?.backend_url ?? '(checking…)'} />
          <InfoRow label="Status" value={health?.status ?? '—'} />
          <InfoRow label="Backend version" value={health?.version ?? '—'} />

          {connectivity === 'disconnected' && (
            <View style={styles.offlineNote}>
              <Text style={styles.offlineText}>
                No backend connected. Set EXPO_PUBLIC_BACKEND_URL in your .env
                file to point at the Python FastAPI server.{'\n'}
                Use Demo Mode on the Home screen to test without a backend.
              </Text>
            </View>
          )}

          <TouchableOpacity
            style={styles.checkButton}
            onPress={runCheck}
            disabled={checking}
            accessibilityRole="button"
            accessibilityLabel="Re-check backend connectivity"
          >
            {checking
              ? <ActivityIndicator color={Colors.textOnDark} />
              : <Text style={styles.checkButtonText}>Check Connection</Text>}
          </TouchableOpacity>
        </View>

        {/* App metadata */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>App Information</Text>
          <InfoRow label="App version" value="0.1.0" />
          <InfoRow label="Contract version" value="0.1.0" />
          <InfoRow label="AI model" value="RandomForest v0.1.0 (synthetic)" />
          <InfoRow label="Risk scoring" value="direct_proxy_uncalibrated" />
          <InfoRow label="Thresholds" value="0.25 / 0.50 / 0.75 (provisional)" />
        </View>

        {/* Disclaimer */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Disclaimer</Text>
          <Text style={styles.disclaimerText}>
            AEI is a research prototype. Risk scores are UNCALIBRATED
            decision-support proxies derived from a model trained on
            synthetic data. They are not calibrated flood probabilities.{'\n\n'}
            Routes are not guaranteed safe. Shelter data is synthetic.
            Travel times are approximate.{'\n\n'}
            Do not use this application as the sole source of guidance
            in a real emergency.
          </Text>
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: Colors.divider }}>
      <Text style={{ fontSize: 12, color: Colors.textSecondary }}>{label}</Text>
      <Text style={{ fontSize: 12, fontWeight: '600', color: Colors.textPrimary, maxWidth: '55%', textAlign: 'right' }}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { padding: 16, paddingBottom: 40 },
  heading: { fontSize: 22, fontWeight: '800', color: Colors.textPrimary, marginBottom: 16 },

  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  cardTitle: { fontSize: 15, fontWeight: '700', color: Colors.textPrimary, marginBottom: 8 },

  offlineNote: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 6,
    padding: 10,
    marginTop: 8,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  offlineText: { fontSize: 11, color: Colors.textSecondary, lineHeight: 17 },

  checkButton: {
    backgroundColor: Colors.primary,
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
    marginTop: 12,
  },
  checkButtonText: { color: Colors.textOnDark, fontWeight: '700' },

  disclaimerText: { fontSize: 12, color: Colors.textSecondary, lineHeight: 19 },
});
