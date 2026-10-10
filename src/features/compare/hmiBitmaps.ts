export type BitmapVariant={level:number;language:string;index?:number;name?:string;file?:string;path?:string;reference?:string;status:string;message?:string;asset_id?:string;sha256?:string};
export type BitmapStates=Partial<Record<'released'|'pressed',{source:string;group?:string;offset?:string;dynamic?:boolean;variants:BitmapVariant[]}>>;
export type BitmapAssets=Record<string,{data_uri:string;name:string;file:string;width:number;height:number}>;

export function selectBitmap(states:BitmapStates|undefined,state:'released'|'pressed',level:number,language:string):BitmapVariant|undefined {
  const variants=states?.[state]?.variants||[];
  const selected=variants.filter(item=>item.level===level);
  const list=selected.length?selected:variants.filter(item=>item.level===0);
  return list.find(item=>item.language===language)||list.find(item=>item.language===language.split('-')[0])||list.find(item=>item.language==='neutral')||list.find(item=>item.language==='en')||list[0];
}

export function bitmapLabel(variant:BitmapVariant|undefined):string {
  return variant?.file||variant?.name||variant?.reference||'Bitmap unavailable';
}

export function previewBitmapProperties(props:Record<string,string>,states:BitmapStates|undefined,level:number,language:string):Record<string,string> {
  const result={...props};
  for(const state of ['released','pressed'] as const){
    const variant=selectBitmap(states,state,level,language);if(!variant)continue;
    const prefix='Resolved'+(state==='pressed'?'Pressed':'')+'Bitmap';
    for(const [suffix,value] of Object.entries({Name:variant.name,File:variant.file,Path:variant.path,Index:variant.index,Status:variant.status,SHA256:variant.sha256,Note:variant.message})){
      if(value!==undefined)result[prefix+suffix]=String(value);else delete result[prefix+suffix];
    }
  }
  return result;
}
