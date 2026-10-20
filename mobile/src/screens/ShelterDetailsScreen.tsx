/**
 * ShelterDetailsScreen
 *
 * Shows full information for a single shelter.
 * Synthetic/unverified shelters are labelled as such.
 * Capacity display never claims real-time accuracy.
 */
import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';

import { Colors } from '../theme/colors';
import { SimulatedBanner } from '../components/SimulatedBanner';
import { WarningCard } from '../components/WarningCard';
import type { RootStackParamList } from '../navigation/types';
import type { Shelter, ShelterAssignment } from '../types/api';

type Route = RouteProp<RootStackParamList, 'ShelterDetails'>;

export function ShelterDetailsScreen() {
  const { params } = useRoute<Route>();
  const { shelterId, plan } = params;

  const shelter = plan.shelters.find((s) => s.shelter_id === shelterId);
  const assignments = plan.allocation.assignments.filter(
    (a) => a.shelter_id === shelterId,
  );

  if (!shelter) {
    return (
      <SafeAreaView style={styles.safe}>
        <Text style={styles.errorText}>Shelter {shelterId} not found in plan.</Text>
      </SafeAreaView>
    );
  }

  const capacityPct =
    shelter.capacity > 0
      ? Math.round((shelter.occupied / shelter.capacity) * 100)
      : 0;

  const statusColor =
    shelter.status === 'OPEN' ? Colors.riskLow :
    shelter.status === 'FULL' ? Colors.riskHigh : Colors.riskUnknown;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <SimulatedBanner visible={plan.is_simulated} />
      <ScrollView contentContainerStyle={styles.scroll}>

        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.name}>{shelter.name}</Text>
          <View style={[styles.statusBadge, { backgroundColor: statusColor + '22', borderColor: statusColor }]}>
            <Text style={[styles.statusText, { color: statusColor }]}>{shelter.status}</Text>
          </View>
        </View>

        {shelter.data_source === 'SYNTHETIC' && (
          <WarningCard
            warnings={['This is a SYNTHETIC shelter location. It is not a verified evacuation facility.']}
            severity="warning"
          />
        )}
        {shelter.notes ? (
          <WarningCard warnings={[shelter.notes]} severity="info" />
        ) : null}

        {/* Capacity */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Capacity</Text>
          <View style={styles.capRow}>
            <View style={styles.capBar}>
              <View style={[styles.capFill, { width: `${capacityPct}%` as any, backgroundColor: statusColor }]} />
            </View>
            <Text style={styles.capPct}>{capacityPct}%</Text>
          </View>
          <View style={styles.capStats}>
            <CapStat label="Total" value={shelter.capacity.toString()} />
            <CapStat label="Occupied" value={shelter.occupied.toString()} />
            <CapStat label="Remaining" value={shelter.remaining_capacity.toString()} />
          </View>
          <Text style={styles.capNote}>
            Capacity figures are from the synthetic dataset and do not reflect real-time occupancy.
          </Text>
        </View>

        {/* Location */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Location</Text>
          <InfoRow label="Latitude" value={shelter.lat.toFixed(6)} />
          <InfoRow label="Longitude" value={shelter.lon.toFixed(6)} />
          <InfoRow label="Nearest node" value={shelter.nearest_node ?? 'unknown'} />
          <InfoRow label="Data source" value={shelter.data_source} />
          <Text style={styles.locationNote}>
            Coordinates are synthetic and do not correspond to a real place.
            A map view requires expo-maps (not yet installed).
          </Text>
        </View>

        {/* Assignments from current plan */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Current Allocations (this plan)</Text>
          {assignments.length === 0 ? (
            <Text style={styles.noAssignments}>No demand assigned to this shelter in the current plan.</Text>
          ) : (
            assignments.map((a, i) => <AssignmentRow key={i} assignment={a} />)
          )}
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}

function CapStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <Text style={{ fontSize: 9, color: Colors.textMuted, textTransform: 'uppercase' }}>{label}</Text>
      <Text style={{ fontSize: 18, fontWeight: '700', color: Colors.textPrimary }}>{value}</Text>
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: Colors.divider }}>
      <Text style={{ fontSize: 12, color: Colors.textSecondary }}>{label}</Text>
      <Text style={{ fontSize: 12, fontWeight: '600', color: Colors.textPrimary }}>{value}</Text>
    </View>
  );
}

function AssignmentRow({ assignment }: { assignment: ShelterAssignment }) {
  return (
    <View style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: Colors.divider }}>
      <Text style={{ fontSize: 13, fontWeight: '600', color: Colors.textPrimary }}>{assignment.demand_id}</Text>
      <Text style={{ fontSize: 11, color: Colors.textSecondary }}>
        {assignment.admitted} / {assignment.requested} admitted ·
        route cost {(assignment.route_cost_m / 1000).toFixed(1)} km
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { padding: 16, paddingBottom: 40 },
  errorText: { padding: 24, color: Colors.error, fontSize: 14 },

  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 },
  name: { fontSize: 20, fontWeight: '800', color: Colors.textPrimary, flex: 1, marginRight: 12 },
  statusBadge: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  statusText: { fontSize: 12, fontWeight: '700' },

  card: { backgroundColor: Colors.surface, borderRadius: 12, padding: 16, marginTop: 12, borderWidth: 1, borderColor: Colors.border },
  cardTitle: { fontSize: 14, fontWeight: '700', color: Colors.textPrimary, marginBottom: 10 },

  capRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  capBar: { flex: 1, height: 10, backgroundColor: Colors.surfaceElevated, borderRadius: 5, overflow: 'hidden' },
  capFill: { height: '100%', borderRadius: 5 },
  capPct: { fontSize: 13, fontWeight: '700', color: Colors.textSecondary, width: 36, textAlign: 'right' },
  capStats: { flexDirection: 'row', marginBottom: 8 },
  capNote: { fontSize: 10, color: Colors.textMuted, fontStyle: 'italic' },

  locationNote: { fontSize: 10, color: Colors.textMuted, fontStyle: 'italic', marginTop: 8 },
  noAssignments: { fontSize: 12, color: Colors.textMuted, fontStyle: 'italic' },
});
