import type { Hazard, Point, Route, Area } from './engine';

export const disasterStyles = {
  Flood: { icon: '🌊', name: 'Flood', zone: 'FLOOD ZONE', color: '#1667bc', fill: '#349fea42', background: '#eaf4ff', message: 'Flooding nearby', advice: 'Keep away from floodwater. Follow the marked route.', texture: '≋' },
  Fire: { icon: '🔥', name: 'Fire', zone: 'FIRE ZONE', color: '#c44520', fill: '#f36d3945', background: '#fff0e8', message: 'Fire reported nearby', advice: 'Keep away from flames and smoke. Follow the marked route.', texture: '🔥' },
  Cyclone: { icon: '🌀', name: 'Cyclone', zone: 'CYCLONE ZONE', color: '#7550b9', fill: '#9b7ed448', background: '#f3edff', message: 'Cyclone-affected area', advice: 'Avoid the marked impact area. Follow the shelter route.', texture: '🌀' },
  Earthquake: { icon: '⚡', name: 'Earthquake', zone: 'DAMAGE ZONE', color: '#ae670b', fill: '#e4a53948', background: '#fff5df', message: 'Earthquake damage nearby', advice: 'Keep away from damaged structures and blocked roads.', texture: '╱╲' },
  Landslide: { icon: '⛰️', name: 'Landslide', zone: 'LANDSLIDE ZONE', color: '#895634', fill: '#af784448', background: '#f6eee6', message: 'Landslide risk nearby', advice: 'Avoid affected slopes and roads. Follow the marked route.', texture: '⛰️' },
} as const;
export type DisasterType = keyof typeof disasterStyles;
export function disasterVisual(type: string) {
  return disasterStyles[type as DisasterType] || disasterStyles.Flood;
}
export function hazardTexturePoints(hazard: Hazard): Point[] {
  const factor = Math.max(0.15, Math.cos(hazard.lat * Math.PI / 180));
  return [[-.58, .12], [.58, .12], [0, -.55]].map(([x, y]) => ({
    lat: hazard.lat + y * hazard.radius / 111320,
    lon: hazard.lon + x * hazard.radius / (111320 * factor),
  }));
}
export { guidance as routeGuidance } from './engine';
export function routeSummary(area: Area) {
  const zones = area.hazards.filter(h => h.active).length;
  const closed = area.roads.filter(r => r.status === 'BLOCKED').length;
  return `${zones} hazard zone${zones === 1 ? '' : 's'} and ${closed} closed road${closed === 1 ? '' : 's'} excluded from route search`;
}
