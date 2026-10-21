import type {Area} from './engine';
export async function loadArea():Promise<Area|null> {
  const value=localStorage.getItem('aei-mobile-preview');
  if (!value) return null;
  const area=JSON.parse(value) as Area;
  if (!area.simulated || !Array.isArray(area.nodes) || !Array.isArray(area.roads)) throw Error('Invalid package');
  return area;
}
export async function saveArea(area:Area) { localStorage.setItem('aei-mobile-preview',JSON.stringify(area)); }
