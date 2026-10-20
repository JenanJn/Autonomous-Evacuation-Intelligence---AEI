/**
 * RouteDetailsScreen
 *
 * Shows full route information and the Simulate Road Blockage control.
 *
 * Requirements enforced:
 * - Blockage button clearly labels its effect BEFORE it is pressed.
 * - After blockage, the replanned route is shown alongside the original.
 * - Route differences are called out explicitly (distance change, new path).
 * - "Not guaranteed safe" disclaimer is always visible.
 * - Unknown risk is shown as UNKNOWN, never as LOW.
 * - The control is clearly labelled SIMULATED when demoMode=true.
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';

import { Colors } from '../theme/colors';
import { SimulatedBanner } from '../components/SimulatedBanner';
import { RiskBadge } from '../components/RiskBadge';
import { WarningCard } from '../components/WarningCard';
import { simulateBlockage, clearBlockage } from '../services/apiClient';
import type { RootStackParamList } from '../navigation/types';
import type { EvacuationPlan, RouteResult, RiskCategory } from '../types/api';

type Route = RouteProp<RootStackParamList, 'RouteDetails'>;

export function RouteDetailsScreen() {
  const { params } = useRoute<Route>();
  const { demoMode } = params;

  const [plan, setPlan] = useState<EvacuationPlan>(params.plan);
  const [blockageLoading, setBlockageLoading] = useState(false);

  const activeRoute = plan.blockage_active && plan.replanned_route
    ? plan.replanned_route
    : plan.primary_route;

  // ── Toggle blockage ───────────────────────────────────────────────────────
  async function handleToggleBlockage() {
    if (!demoMode && !plan.blockage_active) {
      Alert.alert(
        'Road Blockage Simulation',
        'This will simulate a road closure and calculate an alternative route. Continue?',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Simulate', onPress: applyBlockage },
        ],
      );
      return;
    }
    if (plan.blockage_active) {
      await applyUnblock();
    } else {
      await applyBlockage();
    }
  }

  async function applyBlockage() {
    setBlockageLoading(true);
    try {
      const updated = await simulateBlockage(plan, demoMode);
      setPlan(updated);
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : 'Blockage simulation failed');
    } finally {
      setBlockageLoading(false);
    }
  }

  async function applyUnblock() {
    setBlockageLoading(true);
    try {
      const updated = await clearBlockage(demoMode);
      setPlan(updated);
    } finally {
      setBlockageLoading(false);
    }
  }

  const distanceDelta = plan.replanned_route
    ? plan.replanned_route.total_length_m - plan.primary_route.total_length_m
    : 0;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <SimulatedBanner visible={plan.is_simulated} />

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Blockage control */}
        <View style={[
          styles.blockageCard,
          plan.blockage_active ? styles.blockageCardActive : null,
        ]}>
          <View style={styles.blockageHeader}>
            <Text style={styles.blockageTitle}>
              {plan.blockage_active ? '🚧 Blockage Active' : '🛣  Road Simulation'}
            </Text>
            {demoMode && (
              <View style={styles.simPill}>
                <Text style={styles.simPillText}>SIMULATED</Text>
              </View>
            )}
          </View>

          <Text style={styles.blockageDesc}>
            {plan.blockage_active
              ? `Road A → B is blocked. Route has been replanned via ${plan.replanned_route?.path.join(' → ')}.`
              : 'Simulate a road closure to see how the route adapts.'}
          </Text>

          {plan.blockage_active && plan.replanned_route && (
            <View style={styles.deltaRow}>
              <Text style={styles.deltaLabel}>Distance change:</Text>
              <Text style={[
                styles.deltaValue,
                { color: distanceDelta > 0 ? Colors.riskModerate : Colors.riskLow },
              ]}>
                {distanceDelta > 0 ? '+' : ''}{(distanceDelta / 1000).toFixed(1)} km
              </Text>
            </View>
          )}

          <TouchableOpacity
            style={[
              styles.blockageButton,
              plan.blockage_active ? styles.blockageButtonClear : styles.blockageButtonActivate,
              blockageLoading ? styles.blockageButtonDisabled : null,
            ]}
            onPress={handleToggleBlockage}
            disabled={blockageLoading}
            accessibilityRole="button"
            accessibilityLabel={
              plan.blockage_active
                ? 'Clear simulated road blockage'
                : 'Simulate road blockage on segment A to B'
            }
          >
            {blockageLoading
              ? <ActivityIndicator color={Colors.textOnDark} />
              : <Text style={styles.blockageButtonText}>
                  {plan.blockage_active ? 'Clear Blockage' : 'Simulate Road Blockage (A → B)'}
                </Text>
            }
          </TouchableOpacity>
        </View>

        {/* All warnings (including blockage note) */}
        <WarningCard warnings={plan.warnings} severity="warning" />

        {/* Active route detail */}
        <RouteCard
          route={activeRoute}
          label={plan.blockage_active ? 'Replanned Route' : 'Primary Route'}
          highlight={plan.blockage_active}
          zoneRisks={plan.zone_risks.reduce<Record<string, RiskCategory>>(
            (acc, z) => { acc[z.zone_id] = z.risk_category; return acc; }, {}
          )}
        />

        {/* Original route (shown for comparison when blocked) */}
        {plan.blockage_active && (
          <RouteCard
            route={plan.primary_route}
            label="Original Route (blocked)"
            dimmed
            zoneRisks={{}}
          />
        )}

        {/* Safety disclaimer — always shown */}
        <View style={styles.safetyDisclaimer}>
          <Text style={styles.safetyText}>
            ⚠  Routes are NOT guaranteed safe. Risk scores are uncalibrated
            decision-support proxies. Travel times use a fixed speed table and
            do not account for traffic or emergency conditions.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── RouteCard sub-component ────────────────────────────────────────────────

interface RouteCardProps {
  route: RouteResult;
  label: string;
  highlight?: boolean;
  dimmed?: boolean;
  zoneRisks: Record<string, RiskCategory>;
}

function RouteCard({ route, label, highlight, dimmed, zoneRisks }: RouteCardProps) {
  return (
    <View style={[
      cardStyles.card,
      highlight ? cardStyles.cardHighlight : null,
      dimmed ? cardStyles.cardDimmed : null,
    ]}>
      <View style={cardStyles.header}>
        <Text style={[cardStyles.label, dimmed ? cardStyles.labelDimmed : null]}>{label}</Text>
        {route.replanned && (
          <View style={cardStyles.replannedPill}>
            <Text style={cardStyles.replannedText}>REPLANNED</Text>
          </View>
        )}
      </View>

      {!route.feasible && (
        <WarningCard
          warnings={['This route is not feasible.', ...route.notes]}
          severity="error"
        />
      )}

      {route.feasible && (
        <>
          {/* Path */}
          <View style={cardStyles.pathRow}>
            {route.path.map((node, i) => (
              <React.Fragment key={`${node}-${i}`}>
                <View style={[
                  cardStyles.nodeBox,
                  zoneRisks[`ZONE_${node}`] === 'HIGH' || zoneRisks[`ZONE_${node}`] === 'CRITICAL'
                    ? cardStyles.nodeBoxHigh : null,
                ]}>
                  <Text style={cardStyles.nodeText}>{node}</Text>
                </View>
                {i < route.path.length - 1 && (
                  <Text style={cardStyles.arrow}>›</Text>
                )}
              </React.Fragment>
            ))}
          </View>

          {/* Stats */}
          <View style={cardStyles.stats}>
            <Stat label="Distance" value={`${(route.total_length_m / 1000).toFixed(2)} km`} />
            <Stat label="Est. time" value={formatTime(route.estimated_travel_time_s)} sub="approx" />
            <Stat label="Risk penalty" value={`${(route.total_risk_penalty_m / 1000).toFixed(2)} km`} />
            <Stat label="Mode" value={route.mode} />
          </View>

          {/* Per-edge risk breakdown */}
          <Text style={cardStyles.edgesTitle}>Segments</Text>
          {route.edges.map(([u, v], i) => {
            const riskCat = zoneRisks[`ZONE_${u}`] ?? 'UNKNOWN';
            return (
              <View key={i} style={cardStyles.edgeRow}>
                <Text style={cardStyles.edgeLabel}>{u} → {v}</Text>
                <RiskBadge category={riskCat} size="sm" />
              </View>
            );
          })}

          {route.notes.length > 0 && (
            <WarningCard warnings={route.notes} severity="info" />
          )}
        </>
      )}
    </View>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <View style={cardStyles.statItem}>
      <Text style={cardStyles.statLabel}>{label}</Text>
      <Text style={cardStyles.statValue}>{value}</Text>
      {sub && <Text style={cardStyles.statSub}>{sub}</Text>}
    </View>
  );
}

function formatTime(s: number): string {
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  return `${m} min`;
}

// ── Styles ─────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { padding: 16, paddingBottom: 40 },

  blockageCard: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: Colors.border,
    marginBottom: 8,
  },
  blockageCardActive: { borderColor: Colors.riskHigh, backgroundColor: Colors.riskHighBg },
  blockageHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  blockageTitle: { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },
  blockageDesc: { fontSize: 12, color: Colors.textSecondary, marginBottom: 12, lineHeight: 18 },

  deltaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  deltaLabel: { fontSize: 12, color: Colors.textSecondary },
  deltaValue: { fontSize: 14, fontWeight: '700' },

  simPill: {
    backgroundColor: Colors.simulatedBg,
    borderWidth: 1,
    borderColor: Colors.simulated,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  simPillText: { fontSize: 9, fontWeight: '700', color: Colors.simulated },

  blockageButton: {
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
  },
  blockageButtonActivate: { backgroundColor: Colors.riskHigh },
  blockageButtonClear: { backgroundColor: Colors.riskLow },
  blockageButtonDisabled: { opacity: 0.6 },
  blockageButtonText: { color: Colors.textOnDark, fontWeight: '700', fontSize: 14 },

  safetyDisclaimer: {
    marginTop: 16,
    padding: 12,
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  safetyText: { fontSize: 10, color: Colors.textMuted, lineHeight: 15, textAlign: 'center' },
});

const cardStyles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginTop: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cardHighlight: { borderColor: Colors.primaryLight, borderWidth: 2 },
  cardDimmed: { opacity: 0.55 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  label: { fontSize: 15, fontWeight: '700', color: Colors.textPrimary },
  labelDimmed: { color: Colors.textMuted },
  replannedPill: {
    backgroundColor: Colors.riskModerateBg,
    borderWidth: 1,
    borderColor: Colors.riskModerate,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  replannedText: { fontSize: 9, fontWeight: '700', color: Colors.riskModerate },

  pathRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 4, marginBottom: 12 },
  nodeBox: {
    backgroundColor: Colors.primary,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  nodeBoxHigh: { backgroundColor: Colors.riskHigh },
  nodeText: { color: Colors.textOnDark, fontWeight: '700', fontSize: 14 },
  arrow: { fontSize: 16, color: Colors.textMuted },

  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  statItem: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
    alignItems: 'center',
    minWidth: 70,
    flex: 1,
  },
  statLabel: { fontSize: 9, color: Colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.3 },
  statValue: { fontSize: 13, fontWeight: '700', color: Colors.textPrimary, marginTop: 2 },
  statSub: { fontSize: 9, color: Colors.textMuted, fontStyle: 'italic' },

  edgesTitle: { fontSize: 12, fontWeight: '600', color: Colors.textSecondary, marginBottom: 6 },
  edgeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  edgeLabel: { fontSize: 13, color: Colors.textPrimary, fontWeight: '500' },
});
