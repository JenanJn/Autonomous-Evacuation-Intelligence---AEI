/**
 * AEI colour palette.
 * Risk-category colours follow accessibility contrast guidelines (WCAG AA).
 */
export const Colors = {
  // Brand
  primary: '#1a3a6e',
  primaryLight: '#2d5499',
  primaryDark: '#0f2040',
  accent: '#e8880a',

  // Background & surface
  background: '#f4f6fb',
  surface: '#ffffff',
  surfaceElevated: '#eef1f8',
  border: '#d0d8e8',

  // Text
  textPrimary: '#0f1f3d',
  textSecondary: '#4a5a7a',
  textMuted: '#8090b0',
  textOnDark: '#ffffff',

  // Risk categories — used consistently across all displays
  riskLow: '#2e7d32',       // green
  riskLowBg: '#e8f5e9',
  riskModerate: '#ef6c00',  // orange
  riskModerateBg: '#fff3e0',
  riskHigh: '#c62828',      // red
  riskHighBg: '#ffebee',
  riskCritical: '#6a1b9a',  // purple
  riskCriticalBg: '#f3e5f5',
  riskUnknown: '#546e7a',   // grey-blue — NEVER shown as safe
  riskUnknownBg: '#eceff1',

  // Status
  success: '#2e7d32',
  warning: '#f57f17',
  error: '#b71c1c',
  info: '#0277bd',

  // Simulated / demo badge
  simulated: '#7b1fa2',
  simulatedBg: '#f3e5f5',

  // Misc
  divider: '#e0e6f0',
  overlay: 'rgba(0,0,0,0.4)',
  shadow: '#000',
} as const;
