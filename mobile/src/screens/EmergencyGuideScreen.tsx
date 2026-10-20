/**
 * EmergencyGuideScreen — Basic Safety Guide
 *
 * General principles only. No app-specific routing advice is presented
 * as guaranteed safe. Every tip includes the source/caveat.
 */
import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Colors } from '../theme/colors';

const GUIDE_SECTIONS = [
  {
    icon: '🚨',
    title: 'Before Evacuating',
    items: [
      'Follow official emergency authority instructions first. This app provides decision support only.',
      'Gather essentials: water, medication, documents, phone charger (aim for 72-hour kit).',
      'Notify a contact outside the affected area of your intended route and destination.',
      'Check official shelter designations from your local emergency management authority.',
    ],
  },
  {
    icon: '🛣',
    title: 'On the Route',
    items: [
      'Never drive through flooded roads. Turn around, don\'t drown — 6 inches of water can stall a car.',
      'Routes shown in this app are based on synthetic or unvalidated data. Always verify with local authorities.',
      'Travel times shown are approximations using a fixed speed table — actual conditions vary.',
      'If your planned route is blocked, seek official guidance before improvising.',
    ],
  },
  {
    icon: '🏠',
    title: 'At the Shelter',
    items: [
      'Confirm the shelter is officially open with local emergency services before travel.',
      'Shelter data in this app is synthetic — locations and capacities are not verified.',
      'Bring your own supplies where possible to reduce demand on shelter resources.',
      'Register with shelter staff on arrival so authorities can account for evacuees.',
    ],
  },
  {
    icon: '📱',
    title: 'About This App',
    items: [
      'AEI is a research prototype. All risk scores are UNCALIBRATED decision-support proxies.',
      'Risk categories (LOW/MODERATE/HIGH/CRITICAL) are based on provisional thresholds that have not been validated against real flood data.',
      'UNKNOWN risk is shown as UNKNOWN — it never defaults to LOW. Missing data is not treated as safety.',
      'Do not use this app as your sole source of emergency information.',
    ],
  },
];

export function EmergencyGuideScreen() {
  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.heading}>Emergency Safety Guide</Text>
        <View style={styles.disclaimer}>
          <Text style={styles.disclaimerText}>
            This guide provides general principles. Always follow official emergency
            authority instructions. This app does not replace professional emergency management.
          </Text>
        </View>

        {GUIDE_SECTIONS.map((section) => (
          <View key={section.title} style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionIcon}>{section.icon}</Text>
              <Text style={styles.sectionTitle}>{section.title}</Text>
            </View>
            {section.items.map((item, i) => (
              <View key={i} style={styles.itemRow}>
                <Text style={styles.bullet}>•</Text>
                <Text style={styles.itemText}>{item}</Text>
              </View>
            ))}
          </View>
        ))}

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            In a real emergency: contact local emergency services, national disaster hotlines,
            or your country's civil protection authority.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.background },
  scroll: { padding: 16, paddingBottom: 40 },
  heading: { fontSize: 22, fontWeight: '800', color: Colors.textPrimary, marginBottom: 12 },

  disclaimer: {
    backgroundColor: '#fff3cd',
    borderLeftWidth: 4,
    borderLeftColor: Colors.warning,
    borderRadius: 6,
    padding: 12,
    marginBottom: 16,
  },
  disclaimerText: { fontSize: 12, color: '#856404', lineHeight: 18 },

  section: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  sectionIcon: { fontSize: 22, marginRight: 10 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: Colors.textPrimary },

  itemRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 8 },
  bullet: { fontSize: 14, color: Colors.primary, marginRight: 8, marginTop: 1 },
  itemText: { flex: 1, fontSize: 13, color: Colors.textSecondary, lineHeight: 19 },

  footer: {
    backgroundColor: Colors.surfaceElevated,
    borderRadius: 8,
    padding: 14,
    marginTop: 4,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  footerText: { fontSize: 12, color: Colors.textSecondary, textAlign: 'center', lineHeight: 18 },
});
