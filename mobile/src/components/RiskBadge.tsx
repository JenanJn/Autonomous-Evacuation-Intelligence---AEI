/**
 * RiskBadge — displays a risk category with appropriate colour.
 *
 * Critical rule: UNKNOWN must never look like LOW risk.
 * The badge text and colour for UNKNOWN explicitly says "UNKNOWN".
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors } from '../theme/colors';
import type { RiskCategory } from '../types/api';

interface Props {
  category: RiskCategory;
  score?: number | null;
  /** If true, shows a disclaimer that this is not a calibrated probability. */
  showDisclaimer?: boolean;
  size?: 'sm' | 'md';
}

const CATEGORY_CONFIG: Record<RiskCategory, { label: string; color: string; bg: string }> = {
  LOW:      { label: 'LOW',      color: Colors.riskLow,      bg: Colors.riskLowBg },
  MODERATE: { label: 'MODERATE', color: Colors.riskModerate, bg: Colors.riskModerateBg },
  HIGH:     { label: 'HIGH',     color: Colors.riskHigh,     bg: Colors.riskHighBg },
  CRITICAL: { label: 'CRITICAL', color: Colors.riskCritical, bg: Colors.riskCriticalBg },
  UNKNOWN:  { label: 'UNKNOWN',  color: Colors.riskUnknown,  bg: Colors.riskUnknownBg },
};

export function RiskBadge({ category, score, showDisclaimer = false, size = 'md' }: Props) {
  const cfg = CATEGORY_CONFIG[category];
  const isSmall = size === 'sm';

  return (
    <View>
      <View style={[styles.badge, { backgroundColor: cfg.bg, borderColor: cfg.color }]}>
        <Text style={[styles.label, { color: cfg.color, fontSize: isSmall ? 10 : 12 }]}>
          {cfg.label}
        </Text>
        {score != null && (
          <Text style={[styles.score, { color: cfg.color, fontSize: isSmall ? 9 : 11 }]}>
            {' '}({score.toFixed(2)})
          </Text>
        )}
      </View>
      {showDisclaimer && (
        <Text style={styles.disclaimer}>
          Uncalibrated proxy — not a flood probability
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  label: {
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  score: {
    fontWeight: '500',
  },
  disclaimer: {
    fontSize: 9,
    color: Colors.textMuted,
    marginTop: 2,
    fontStyle: 'italic',
  },
});
