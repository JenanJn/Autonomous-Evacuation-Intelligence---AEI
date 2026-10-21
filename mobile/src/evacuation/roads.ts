import type { Point,Area,TravelMode } from './engine';
import { buildArea } from './network';
const defaults=['https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter'];
export async function downloadArea(point:Point,type:string,signal?:AbortSignal,mode:TravelMode='walking'):Promise<Area>{
 if(!Number.isFinite(point.lat)||!Number.isFinite(point.lon)||Math.abs(point.lat)>85||Math.abs(point.lon)>180)throw Error('Choose valid map coordinates.');
 const around=`(around:1600,${point.lat},${point.lon})`;
 const query=`[out:json][timeout:30];(way[highway]${around};nwr[amenity~"^(school|community_centre|townhall|place_of_worship|hospital|clinic)$"]${around};way[building]${around};way[natural=water]${around};way[leisure=park]${around};);out body center;>;out skel qt;`;
 const endpoints=process.env.EXPO_PUBLIC_OVERPASS_URL?[process.env.EXPO_PUBLIC_OVERPASS_URL]:defaults;
 let last='Road download unavailable.';
 for(const endpoint of endpoints){
  if(signal?.aborted)throw Error('Download cancelled.');
  const controller=new AbortController();const cancel=()=>controller.abort();signal?.addEventListener('abort',cancel);const timeout=setTimeout(cancel,40000);
  try{const response=await fetch(endpoint+'?data='+encodeURIComponent(query),{headers:{'User-Agent':'AEI-Evacuation/0.4 (+https://github.com/JenanJn/Autonomous-Evacuation-Intelligence-or-AEI-.)'},signal:controller.signal});if(!response.ok)throw Error(`Road service returned ${response.status}. Try again later.`);const data=await response.json();if(data.remark)throw Error('The road service could not complete this area download. Try again or select a less dense area.');return buildArea(data,point,type,mode);}
  catch(error){last=error instanceof Error?error.message:last;if(signal?.aborted)throw Error('Download cancelled.');}
  finally{clearTimeout(timeout);signal?.removeEventListener('abort',cancel);}
 }
 throw Error(last+' Internet is needed to prepare a new area. Saved areas remain available.');
}
