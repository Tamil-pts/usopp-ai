export function documentFilename(number:string|undefined,revision:string|number,format:string,id='document'){
 const clean=(value:string,limit:number)=>value.replace(/[<>:"/\\|?*\x00-\x1f]/g,'-').replace(/^[ .]+|[ .]+$/g,'').slice(0,limit).replace(/[ .]+$/g,'')||'Document';
 const label=typeof revision==='number'?'R'+String(revision).padStart(2,'0'):revision;
 return clean(number||'Native-'+id.slice(0,8).toUpperCase(),150)+'-'+clean(label,30)+'.'+format;
}
