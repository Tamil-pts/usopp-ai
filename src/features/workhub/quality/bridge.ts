let active:{project:string;flush:()=>Promise<void>}|null=null;
export function registerQualityDraft(project:string,flush:()=>Promise<void>){const entry={project,flush};active=entry;return()=>{if(active===entry)active=null;};}
export async function flushQualityDraft(){if(active)await active.flush();}
