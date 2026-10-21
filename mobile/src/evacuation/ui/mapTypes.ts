import type { Area, Point, Route } from '../engine';
export interface MapHandle { focus:(point?:Point)=>void; overview:()=>void }
export interface MapProps { area:Area; position:Point; positionLabel:string; selectedId:string|null; route:Route|null; schematic:boolean; bottomSpace:number; onShelter:(id:string)=>void; onHazard:()=>void; onManual:(point:Point)=>void; navigating:boolean; focusRoute:boolean; compact:boolean; onPan?:()=>void }
