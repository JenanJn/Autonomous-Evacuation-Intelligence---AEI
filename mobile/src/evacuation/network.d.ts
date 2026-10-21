import type {Area,Point,Hazard,TravelMode} from './engine';
export function emptyArea(point?:Point,type?:string):Area;
export function buildArea(data:{elements:any[]},origin:Point,type?:string,mode?:TravelMode):Area;
export function makeHazards(area:Area,type?:string,growth?:number):Hazard[];
export function offset(point:Point,x:number,y:number):Point;
