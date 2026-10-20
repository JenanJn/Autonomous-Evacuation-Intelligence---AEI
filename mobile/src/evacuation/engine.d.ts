export interface Point {lat:number;lon:number}
export interface Node extends Point {id:string}
export interface Road {id:string;u:string;v:string;distance:number;status:string;risk:number;accessible:boolean}
export interface Shelter extends Point {id:string;name:string;node:string;capacity:number;available:number;status:string;medical:boolean;food:boolean;water:boolean;toilets:boolean;accessible:boolean;address:string;contact:string}
export interface Hazard extends Point {id:string;type:string;severity:string;radius:number;active:boolean}
export interface Area {version:number;updated:string;simulated:boolean;origin:Point;nodes:Node[];roads:Road[];shelters:Shelter[];hazards:Hazard[];facilities:(Point & {name:string;type:string})[];alerts:string[]}
export interface Route {path:string[];edges:string[];distance:number;cost:number;minutes:number;snapDistance:number}
export interface Option {shelter:Shelter;route:Route}
export function scenario(lat?:number,lon?:number,type?:string):Area;
export function metres(a:Point,b:Point):number;
export function route(s:Area,p:Point,dest:string,accessible?:boolean):Route|null;
export function options(s:Area,p:Point,accessible?:boolean):Option[];
export function intersects(a:Point,b:Point,h:Hazard):boolean;
