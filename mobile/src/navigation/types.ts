/**
 * React Navigation typed param lists.
 * Keep this file in sync with every navigator definition.
 */

import type { EvacuationPlan, UserLocation } from '../types/api';

// ── Root stack ─────────────────────────────────────────────────────────────

export type RootStackParamList = {
  Home: undefined;
  EvacuationMap: undefined;
  DemoSetup: {startMode?:'gps'|'map'};
  LocationSelection: {disaster?:import('../evacuation/presentation').DisasterType} | undefined;
  EvacuationPlan: {
    location: UserLocation;
    demoMode: boolean;
  };
  RouteDetails: {
    plan: EvacuationPlan;
    demoMode: boolean;
  };
  ShelterDetails: {
    shelterId: string;
    plan: EvacuationPlan;
  };
  EmergencyGuide: undefined;
  Settings: undefined;
};

// Allow TypeScript to find our custom navigation types.
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}
