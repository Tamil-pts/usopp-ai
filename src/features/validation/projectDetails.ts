export type ProjectDetails={
  projectName:string;
  projectPath:string;
  projectFiles:string[];
  automationStudioVersion:string|null;
  activeConfiguration:string|null;
  plcType:string|null;
  screenFolder:string|null;
  screenFolders:string[];
  screenType?:string|null;
  screenHardwareFile?:string|null;
  legacyCpuRoot?:string|null;
  logicScopeMessage?:string;
  settingsFile:string|null;
  configurationStatus:'available'|'missing'|'unavailable';
  configurationMessage:string;
};

const MACHINE_PREFIXES:[string,string][]=[
  ['LDF','Finisher'],['LDB','Breaker'],['LH','Lapformer'],['LF','Speedframe'],
  ['LC','Carding'],['BL','Blow Room'],['LR','Ringframe'],
];
export function inferMachineDepartment(projectFiles:string[]){
  const apj=projectFiles.find(name=>/\.apj$/i.test(name));
  const source=(apj||'').replace(/^.*[\\/]/,'').replace(/\.apj$/i,'').toUpperCase();
  const match=MACHINE_PREFIXES.find(([prefix])=>source.startsWith(prefix));
  return match?.[1]||'All';
}

function parseStudioVersion(text:string,name:string) {
  const clean=text.replace(/\0/g,'');
  const patterns=[/AutomationStudio\s+Version\s*=\s*["']\s*(\d+)\.(\d+)/i,/Version\s+V\s*(\d+)\.(\d+)/i,/Automation\s+Studio[\s\S]{0,80}?(\d+)\.(\d+)/i];
  for(const pattern of patterns){const match=clean.match(pattern);if(match)return `${Number(match[1])}.${match[2]}`;}
  return /\.gdm$/i.test(name)&&clean.startsWith('B&R')?'2.7':null;
}

async function readResponse(response:Response) {
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||'Could not read project details.');
  return data;
}

export async function loadProjectDetails(localPath:string,files:File[],signal:AbortSignal):Promise<ProjectDetails> {
  if(localPath)return readResponse(await fetch('/api/local/project/details',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_path:localPath}),signal,
  }));
  const paths=files.map(file=>({file,path:(file.webkitRelativePath||file.name).replace(/\\/g,'/')}));
  const candidates=new Set<string>();
  for(const {path} of paths){
    if(/\.(apj|gdm)$/i.test(path))candidates.add(path.slice(0,path.lastIndexOf('/')));
    const logical=path.toLowerCase().indexOf('/logical/');
    if(logical>=0)candidates.add(path.slice(0,logical));
  }
  const roots=[...candidates].filter(root=>![...candidates].some(other=>root!==other&&root.startsWith(other+'/')));
  const root=roots.length===1?roots[0]:(paths[0]?.path.split('/')[0]||'Uploaded project');
  const info:ProjectDetails={projectName:root.split('/').pop()||root,projectPath:root,
    projectFiles:paths.filter(p=>p.path.slice(0,p.path.lastIndexOf('/'))===root&&/\.(apj|gdm)$/i.test(p.path)).map(p=>p.file.name),
    automationStudioVersion:null,
    activeConfiguration:null,plcType:null,screenFolder:null,screenFolders:[],settingsFile:null,configurationStatus:'missing',configurationMessage:'LastUser.set was not included in the selected project root.'};
  if(roots.length>1)return {...info,configurationStatus:'unavailable',configurationMessage:'Multiple project roots were selected. Select one project to show its active configuration.'};
  const descriptor=paths.find(p=>p.path.slice(0,p.path.lastIndexOf('/'))===root&&/\.(apj|gdm)$/i.test(p.path));
  if(descriptor)info.automationStudioVersion=parseStudioVersion(await descriptor.file.text(),descriptor.file.name);
  const settings=paths.find(p=>p.path.toLowerCase()===`${root}/lastuser.set`.toLowerCase());
  let data:Pick<ProjectDetails,'activeConfiguration'|'settingsFile'|'configurationStatus'|'configurationMessage'>={
    activeConfiguration:null,settingsFile:null,configurationStatus:info.configurationStatus,configurationMessage:info.configurationMessage};
  if(settings){
    const form=new FormData();form.append('settings_file',settings.file,settings.path);
    data=await readResponse(await fetch('/api/project/last-user',{method:'POST',body:form,signal}));
  }
  const relative=paths.map(item=>({...item,relative:item.path.slice(root.length+1)}));
  const legacy=!!info.automationStudioVersion?.startsWith('2.');
  const configurations=[...new Set(relative.map(item=>item.relative.match(/^Physical\/([^/]+)\//i)?.[1]).filter(Boolean) as string[])]
    .filter(name=>!['system','visualcomponents','temp'].includes(name.toLowerCase()));
  if(legacy&&!settings){
    data=configurations.length===1?{...data,activeConfiguration:configurations[0],configurationStatus:'available',
      configurationMessage:'Selected the single AS 2.7 physical configuration; LastUser.set is not required.'}:
      {...data,configurationStatus:'unavailable',configurationMessage:'AS 2.7 requires one physical configuration; selection is unresolved.'};
  }
  const cpus=[...new Set(relative.map(item=>item.relative.match(/^(pgm\/[^/]+\/CPU)\//i)?.[1]).filter(Boolean) as string[])];
  const legacyCpuRoot=legacy&&configurations.length===1&&cpus.length===1&&configurations[0].toLowerCase()===data.activeConfiguration?.toLowerCase()?cpus[0]:null;
  const logicScopeMessage=legacy&&!legacyCpuRoot?'AS 2.7 CPU ownership is unresolved. Expected one physical configuration and one pgm/<project>/CPU folder; CPU sources were not selected.':'';
  const screenFolders=[...new Set(relative.map(item=>item.relative.match(/^Logical\/([^/]+)\/Pages\//i)?.[1]).filter(Boolean) as string[])].sort();
  const physicalPrefix=data.activeConfiguration?`${root}/Physical/${data.activeConfiguration}/`.toLowerCase():'';
  const hardware=paths.find(item=>physicalPrefix&&item.path.toLowerCase().startsWith(physicalPrefix)&&/\/Hardware\.(hwl|hw)$/i.test(item.path));
  const cpu=paths.find(item=>physicalPrefix&&item.path.toLowerCase().startsWith(physicalPrefix)&&/\/Cpu\.sw$/i.test(item.path));
  let plcType:string|null=null;
  if(hardware){
    const document=new DOMParser().parseFromString(await hardware.file.text(),'application/xml');
    const plc=Array.from(document.getElementsByTagName('*')).find(node=>node.localName.toLowerCase()==='module'&&(node.getAttribute('Name')||'').toLowerCase()==='plc1');
    plcType=plc?.getAttribute('Type')||null;
  }
  const configured=cpu?[...((await cpu.file.text()).matchAll(/<VcDataObject\b[^>]*\bName=["']([^"']+)/gi))].map(match=>match[1]):[];
  const panels:{target:string;type:string|null;file:string}[]=[];
  for(const item of relative){
    if(!physicalPrefix||!item.path.toLowerCase().startsWith(physicalPrefix)||!/\/hw\.cfg$/i.test(item.path))continue;
    const owner=item.relative.split('/').slice(-2)[0];
    const target=screenFolders.find(folder=>folder.toLowerCase()===owner.toLowerCase());
    if(!target)continue;
    const document=new DOMParser().parseFromString(await item.file.text(),'application/xml');
    for(const master of Array.from(document.getElementsByTagName('*')).filter(node=>node.localName.toLowerCase()==='masterpanel')){
      const type=Array.from(master.children).find(node=>node.localName.toLowerCase()==='property'&&(node.getAttribute('Name')||'').toLowerCase()==='type')?.getAttribute('Value')||master.getAttribute('Name');
      panels.push({target,type,file:item.relative});
    }
  }
  const configuredTarget=configured.map(name=>screenFolders.find(folder=>folder.toLowerCase()===name.toLowerCase())).find(Boolean);
  const panelTargets=[...new Set(panels.map(panel=>panel.target))];
  const screenFolder=configuredTarget||(panelTargets.length===1?panelTargets[0]:null)||(screenFolders.length===1?screenFolders[0]:null);
  const selectedPanels=panels.filter(panel=>panel.target===screenFolder);
  const panel=selectedPanels.length===1?selectedPanels[0]:null;
  return {...info,...data,plcType,screenFolder,screenFolders,screenType:panel?.type||null,
    screenHardwareFile:panel?.file||null,legacyCpuRoot,logicScopeMessage};
}
