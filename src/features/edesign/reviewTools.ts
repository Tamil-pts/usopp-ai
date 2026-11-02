export type Shape='rectangle'|'cloud'|'cloud-only'|'arrow'|'note'|'highlight'|'underline'|'marker';
export const shapeOptions:[Shape,string][]=[['cloud','Cloud + arrow + comment'],['cloud-only','Revision cloud only'],['highlight','Highlight + comment'],['underline','Underline'],['marker','Freehand marker'],['rectangle','Rectangle + comment'],['arrow','Arrow'],['note','Comment pin']];
export const regionShape=(shape:Shape)=>['cloud','rectangle','highlight'].includes(shape);
export const optionalComment=(shape:Shape)=>['cloud-only','highlight','underline','marker'].includes(shape);
export const markColor=(mark:{color?:string|null;kind:string})=>mark.color||({modify:'#bb8100',add:'#008152',remove:'#d12b45',comment:'#2369b3'}[mark.kind]||'#2369b3');
export const markOpacity=(mark:{opacity?:number|null;shape:Shape})=>mark.opacity??(mark.shape==='highlight'?.28:mark.shape==='marker'?.7:1);
export const reference=(mark:{reference?:string;referenceNo?:number})=>mark.reference||(mark.referenceNo?'R'+String(mark.referenceNo).padStart(3,'0'):'New');
export const referenceColor=(mark:{color?:string|null;kind:string})=>{const hex=markColor(mark),rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));return rgb[0]*.299+rgb[1]*.587+rgb[2]*.114>175?'#334155':hex};
