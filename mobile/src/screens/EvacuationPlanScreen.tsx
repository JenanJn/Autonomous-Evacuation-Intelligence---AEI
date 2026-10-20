/**
 * EvacuationPlanScreen
 *
 * Shows the full evacuation plan:
 * - SIMULATED banner when demo mode is active
 * - All warnings from the backend (never suppressed)
 * - Zone risk table (all categories shown with correct colours)
 * - Primary route summary
 * - Shelter list with capacity and status
 * - Unassigned demand (never hidden)
 * - Navigation to RouteDetails and ShelterDetails
 *
 * Loading state is shown while the API call is in-flight.
 * Error state shows the raw error message — no silent fallback.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';

import { Colors } from '../theme/colors';
import { SimulatedBanner } from '../components/SimulatedBanner';
import { RiskBadge } from '../components/RiskBadge';
import { WarningCard } from '../components/WarningCard';
import { getEvacuationPlan } from '../services/apiClient';
import type { RootStackParamList } from '../navigation/types';
import type { EvacuationPlan, Shelter } from '../types/api';

type Nav = NativeStackNavigationProp<RootStackParamList, 'EvacuationPlan'>;
type Route = RouteProp<RootStackParamList, 'EvacuationPlan'>;

export function EvacuationPlanScreen() {
  const navigation = useNavigation<Nav>();
  const { params } = useRoute<Route>();
  const { location, demoMode } = params;

  const [plan, setPlan] = useState<EvacuationPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadPlan = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const result = await getEvacuationPlan(location, demoMode);
      setPlan(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error loading plan');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [location, demoMode]);

  useEffect(() => { loadPlan(); }, [loadPlan]);

  // ── Loading state ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <SafeAreaView style={styles.centred}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>
          {demoMode ? 'Loading demo plan…' : 'Calculating evacuation plan…'}
        </Text>
        {demoMode && (
          <Text style={styles.loadingNote}>Using synthetic data</Text>
        )}
      </SafeAreaView>
    );
  }

  // ── Error state ───────────────────────────────────────────────────────────
  if (error || !plan) {
    return (
      <SafeAreaView style={styles.centred}>
        <Text style={styles.errorTitle}>Could not load evacuation plan</Text>
        <Text style={styles.errorMessage}>{error ?? 'No data returned'}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={() => loadPlan()}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
        {!demoMode && (
          <Text style={styles.errorHint}>
            No backend connected. Use Demo Mode on the Home screen to test offline.
          </Text>
        )}
      </SafeAreaView>
    );
  }

  const { primary_route, zone_risks, shelters, allocation, warnings } = plan;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <SimulatedBanner visible={plan.is_simulated} />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => loadPlan(true)} />
        }
      >
        {/* Header */}
        <View style={styles.planHeader}>
          <Text style={styles.planTitle}>Evacuation Plan</Text>
          <Text style={styles.originLabel} numberOfLines={1}>
            From: {plan.origin_label}
          </Text>
          <Text style={styles.generatedAt}>
            Generated: {new Date(plan.generated_at).toLocaleTimeString()}
            {plan.is_simulated ? '  ·  SIMULATED' : ''}
          </Text>
        </View>

        {/* Warnings — never suppressed */}
        <WarningCard warnings={warnings} severity="warning" />

        {/* Route summary card */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>🛣  Primary Route</Text>
            {plan.blockage_active && (
              <View style={styles.blockedPill}>
                <Text style={styles.blockedPillText}>REROUTED</Text>
              </View>
            )}
          </View>

          <View style={styles.routePath}>
            <Text style={styles.routePathText}>
              {primary_route.path.join(' → ')}
            </Text>
          </View>

          <View style={styles.routeStats}>
            <StatChip label="Distance" value={`${(primary_route.total_length_m / 1000).toFixed(1)} km`} />
            <StatChip
              label="Est. time"
              value={formatTime(primary_route.estimated_travel_time_s)}
              note="approx, not validated"
            />
            <StatChip
              label="Risk cost"
              value={`${(primary_route.total_risk_penalty_m / 1000).toFixed(1)} km`}
              note="penalty"
            />
          </View>

          {primary_route.notes.length > 0 && (
            <WarningCard warnings={primary_route.notes} severity="info" />
          )}

          <TouchableOpacity
            style={styles.viewDetailsButton}
            onPress={() => navigation.navigate('RouteDetails', { plan, demoMode })}
            accessibilityRole="button"
            accessibilityLabel="View route details and simulate road blockage"
          >
            <Text style={styles.viewDetailsText}>View Details & Simulate Blockage →</Text>
          </TouchableOpacity>
        </View>

        {/* Zone risk table */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>🌊  Zone Risk Overview</Text>
          <Text style={styles.cardNote}>
            Scores are UNCALIBRATED proxies — not flood probabilities.
          </Text>
          {zone_risks.map((z) => (
            <View key={z.zone_id} style={styles.zoneRow}>
              <Text style={styles.zoneId}>{z.zone_id}</Text>
              <RiskBadge category={z.risk_category} score={z.risk_score} size="sm" />
              <Text style={styles.zoneFreshness}>
                {z.data_freshness ? formatFreshness(z.data_freshness) : '?'}
              </Text>
              {z.risk_status !== 'OK' && (
                <Text style={styles.zoneStatusBad}>{z.risk_status}</Text>
              )}
            </View>
          ))}
        </View>

        {/* Shelters */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>🏠  Shelters</Text>
          <Text style={styles.cardNote}>Synthetic locations — not verified facilities.</Text>
          {shelters.map((s) => (
            <ShelterRow
              key={s.shelter_id}
              shelter={s}
              onPress={() => navigation.navigate('ShelterDetails', {
                shelterId: s.shelter_id,
                plan,
              })}
            />
          ))}

          {/* Unassigned demand — never hidden */}
          {allocation.total_unassigned > 0 && (
            <WarningCard
              warnings={[
                `${allocation.total_unassigned} people could not be assigned to any shelter.`,
                ...allocation.unassigned.map(
                  (u) => `${u.demand_id}: ${u.requested} unassigned — ${u.reason}`,
                ),
              ]}
              severity="error"
            />
          )}

          <View style={styles.allocSummary}>
            <Text style={styles.allocText}>
              {allocation.total_admitted} / {allocation.total_requested} admitted
            </Text>
            <Text style={styles.allocNote}>{allocation.notes[0]}</Text>
          </View>
        </View>

        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatChip({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <View style={statStyles.chip}>
      <Text style={statStyles.label}>{label}</Text>
      <Text style={statStyles.value}>{value}</Text>
      {note && <Text style={statStyles.note}>{note}</Text>}
    </View>
  );
}

function ShelterRow({ shelter, onPress }: { shelter: Shelter; onPress: () => void }) {
  const statusColor =
    shelter.status === 'OPEN' ? Colors.riskLow :
    shelter.status === 'FULL' ? Colors.riskHigh : Colors.riskUnknown;

  const pct = shelter.capacity > 0
    ? Math.round((shelter.occupied / shelter.capacity) * 100)
    : 0;

  return (
    <TouchableOpacity
      style={shelterStyles.row}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`View details for ${shelter.name}`}
    >
      <View style={shelterStyles.left}>
        <Text style={shelterStyles.name} numberOfLines={1}>{shelter.name}</Text>
        <Text style={shelterStyles.capacity}>
          {shelter.remaining_capacity} / {shelter.capacity} remaining  ({pct}% full)
        </Text>
      </View>
      <View style={[shelterStyles.statusDot, { backgroundColor: statusColor }]} />
      <Text style={[shelterStyles.statusText, { color: statusColor }]}>
        {shelter.status}
      </Text>
      <Text style={shelterStyles.arrow}>›</Text>
    </TouchableOpacity>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m} m ${s} s` : `${m} min`;
}

function formatFreshness(iso: string): string {
  // Parse e.g. "PT21600S" → "6 h"
  const match = iso.match(/PT(\d+)S/);
  if (!match) return iso;
  const secs = parseInt(match[1], 10);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (h > 0) return `${h} h ago`;
  if (m > 0) return `${m} min ago`;
  return 'just now';
}

// ── Styles ─────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { flex: 1 },
  scrollContent: { padding: 16, paddingBottom: 32 },

  centred: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24, backgroundColor: Colors.background },
  loadingText: { marginTop: 16, fontSize: 15, color: Colors.textSecondary },
  loadingNote: { marginTop: 6, fontSize: 12, color: Colors.textMuted, fontStyle: 'italic' },
  errorTitle: { fontSize: 18, fontWeight: '700', color: Colors.error, marginBottom: 8 },
  errorMessage: { fontSize: 13, color: Colors.textSecondary, textAlign: 'center', marginBottom: 16 },
  retryButton: { backgroundColor: Colors.primary, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 8 },
  retryText: { color: Colors.textOnDark, fontWeight: '700' },
  errorHint: { marginTop: 16, fontSize: 11, color: Colors.textMuted, textAlign: 'center', fontStyle: 'italic' },

  planHeader: { marginBottom: 8 },
  planTitle: { fontSize: 22, fontWeight: '800', color: Colors.textPrimary },
  originLabel: { fontSize: 13, color: Colors.textSecondary, marginTop: 2 },
  generatedAt: { fontSize: 11, color: Colors.textMuted, marginTop: 2 },

  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginTop: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    shadowColor: Colors.shadow,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  cardTitle: { fontSize: 15, fontWeight: '700', color: Colors.textPrimary, marginBottom: 4 },
  cardNote: { fontSize: 10, color: Colors.textMuted, fontStyle: 'italic', marginBottom: 10 },

  blockedPill: {
    backgroundColor: Colors.riskHighBg,
    borderWidth: 1,
    borderColor: Colors.riskHigh,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  blockedPillText: { fontSize: 10, fontWeight: '700', color: Colors.riskHigh },

  routePath: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
  routePathText: { fontSize: 15, fontWeight: '700', color: Colors.primary, letterSpacing: 0.5 },

  routeStats: { flexDirection: 'row', gap: 8, marginBottom: 8, flexWrap: 'wrap' },

  viewDetailsButton: {
    backgroundColor: Colors.primaryLight,
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  viewDetailsText: { color: Colors.textOnDark, fontWeight: '700', fontSize: 14 },

  zoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 7,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
    gap: 8,
  },
  zoneId: { fontSize: 12, fontWeight: '600', color: Colors.textSecondary, width: 72 },
  zoneFreshness: { fontSize: 10, color: Colors.textMuted, marginLeft: 'auto' as any },
  zoneStatusBad: { fontSize: 10, color: Colors.error, fontWeight: '700' },

  allocSummary: { marginTop: 12, paddingTop: 8, borderTopWidth: 1, borderTopColor: Colors.divider },
  allocText: { fontSize: 13, fontWeight: '600', color: Colors.textPrimary },
  allocNote: { fontSize: 10, color: Colors.textMuted, fontStyle: 'italic', marginTop: 2 },
});

const statStyles = StyleSheet.create({
  chip: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    alignItems: 'center',
    flex: 1,
    minWidth: 70,
  },
  label: { fontSize: 9, color: Colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  value: { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginTop: 2 },
  note:  { fontSize: 9, color: Colors.textMuted, fontStyle: 'italic', marginTop: 1 },
});

const shelterStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
    gap: 8,
  },
  left: { flex: 1 },
  name: { fontSize: 13, fontWeight: '600', color: Colors.textPrimary },
  capacity: { fontSize: 11, color: Colors.textSecondary, marginTop: 2 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { fontSize: 11, fontWeight: '700', minWidth: 44 },
  arrow: { fontSize: 18, color: Colors.textMuted },
});
