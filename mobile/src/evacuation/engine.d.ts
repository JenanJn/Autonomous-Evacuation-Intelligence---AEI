export interface Point {lat:number;lon:number}
export interface Node extends Point {id:string}
export type TravelMode='walking'|'driving'|'ambulance';
export interface Road {id:string;u:string;v:string;distance:number;status:string;risk:number;accessible:boolean;walking?:boolean;driving?:boolean;oneway?:number;speedKph?:number;name?:string;highway?:string;way?:string}
export interface Shelter extends Point {id:string;name:string;node:string;capacity:number;available:number;status:string;medical:boolean;food:boolean;water:boolean;toilets:boolean;accessible:boolean;address:string;contact:string;verified?:boolean}
export interface Hazard extends Point {id:string;type:string;severity:string;radius:number;active:boolean;shape?:Point[];growth?:number;description?:string}
export interface Area {version:number;updated:string;simulated:boolean;origin:Point;nodes:Node[];roads:Road[];shelters:Shelter[];hazards:Hazard[];facilities:(Point & {name:string;type:string})[];alerts:string[];networkSource?:string;prepared?:boolean;coverageRadius?:number;downloadedAt?:string;features?:{id:string;kind:string;geometry:Point[]}[];readiness?:{reachable:number;alternativeRoute:boolean}}
export interface Route {path:string[];edges:string[];distance:number;cost:number;minutes:number;snapDistance:number;geometry?:Point[];legDistances?:number[];mode?:TravelMode}
export interface Option {shelter:Shelter;route:Route}
export function scenario(lat?:number,lon?:number,type?:string):Area;
export function metres(a:Point,b:Point):number;
export function route(s:Area,p:Point,dest:string,accessible?:boolean,mode?:TravelMode):Route|null;
export function options(s:Area,p:Point,accessible?:boolean,mode?:TravelMode):Option[];
export function intersects(a:Point,b:Point,h:Hazard):boolean;
export function inside(a:Point,polygon:Point[]):boolean;
export function project(p:Point,a:Point,b:Point):{point:Point;t:number};
export function bearing(a:Point,b:Point):number;
export function guidance(area:Area,route:Route|null):{symbol:string;instruction:string;next:string};
