/**
 * AppNavigator — Root stack navigator.
 *
 * All screens are registered here. Navigation type safety flows through
 * RootStackParamList in navigation/types.ts.
 */
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { Colors } from '../theme/colors';
import { EvacuationMapScreen } from '../screens/EvacuationMapScreen';
import { HomeScreen } from '../screens/HomeScreen';
import { LocationSelectionScreen } from '../screens/LocationSelectionScreen';
import { EvacuationPlanScreen } from '../screens/EvacuationPlanScreen';
import { RouteDetailsScreen } from '../screens/RouteDetailsScreen';
import { ShelterDetailsScreen } from '../screens/ShelterDetailsScreen';
import { EmergencyGuideScreen } from '../screens/EmergencyGuideScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function AppNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="EvacuationMap"
        screenOptions={{
          headerStyle: { backgroundColor: Colors.primary },
          headerTintColor: Colors.textOnDark,
          headerTitleStyle: { fontWeight: '700' },
          contentStyle: { backgroundColor: Colors.background },
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="EvacuationMap" component={EvacuationMapScreen} options={{headerShown:false}} />
        <Stack.Screen
          name="Home"
          component={HomeScreen}
          options={{ headerShown: false }}
        />
        <Stack.Screen
          name="LocationSelection"
          component={LocationSelectionScreen}
          options={{ title: 'Choose Location' }}
        />
        <Stack.Screen
          name="EvacuationPlan"
          component={EvacuationPlanScreen}
          options={{ title: 'Evacuation Plan' }}
        />
        <Stack.Screen
          name="RouteDetails"
          component={RouteDetailsScreen}
          options={{ title: 'Route Details' }}
        />
        <Stack.Screen
          name="ShelterDetails"
          component={ShelterDetailsScreen}
          options={{ title: 'Shelter Details' }}
        />
        <Stack.Screen
          name="EmergencyGuide"
          component={EmergencyGuideScreen}
          options={{ title: 'Emergency Guide' }}
        />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{ title: 'Settings' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
