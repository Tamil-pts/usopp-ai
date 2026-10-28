const active=new Set<{project:string;flush:()=>Promise<void>}>();
export function registerQualityDraft(project:string,flush:()=>Promise<void>){const entry={project,flush};active.add(entry);return()=>{active.delete(entry);};}
export async function flushQualityDraft(){for(const entry of [...active])if(active.has(entry))await entry.flush();}
