import {toolProjectHeaders} from '../../shared/toolProject';
import {userStorage} from '../../shared/userStorage';
import {useEffect,useState} from 'react';
import {logEvent} from '../../shared/logging';

type CompareFiles = {base: File[]; new_: File[]};
type Notify = (message: string) => void;
type ProjectInfo={project_name?:string;automation_studio_version?:string;active_configuration?:string;plc_type?:string;active_hmi?:string;screen_folders?:string[];configured_hmi_objects?:string[]};

async function inspectUploadedProject(files:File[]):Promise<ProjectInfo|null>{
  if(!files.length)return null;
  const paths=files.map(file=>({file,path:(file.webkitRelativePath||file.name).replace(/\\/g,'/')}));
  const first=paths[0]?.path.split('/')[0]||'Uploaded project';
  const settings=paths.find(item=>item.path.toLowerCase()===`${first}/lastuser.set`.toLowerCase());
  const settingsText=settings?await settings.file.text():'';
  const active=settingsText.match(/ActiveConfigurationName\s*=\s*["']([^"']+)/i)?.[1];
  const version=settingsText.match(/AutomationStudio\s+Version\s*=\s*["']?\s*(\d+\.\d+)/i)?.[1];
  const descriptor=paths.find(item=>new RegExp(`^${first.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}/[^/]+\\.(apj|gdm)$`,'i').test(item.path));
  const screenFolders=[...new Set(paths.map(item=>item.path.match(/\/Logical\/([^/]+)\/Pages\//i)?.[1]).filter(Boolean) as string[])].sort();
  const physicalPrefix=active?`${first}/Physical/${active}/`.toLowerCase():'';
  const hardware=paths.find(item=>physicalPrefix&&item.path.toLowerCase().startsWith(physicalPrefix)&&/Hardware\.(hwl|hw)$/i.test(item.path));
  const cpu=paths.find(item=>physicalPrefix&&item.path.toLowerCase().startsWith(physicalPrefix)&&/\/Cpu\.sw$/i.test(item.path));
  const hardwareText=hardware?await hardware.file.text():'';const cpuText=cpu?await cpu.file.text():'';
  const plcType=hardwareText.match(/<Module\b[^>]*\bName=["']PLC1["'][^>]*\bType=["']([^"']+)/i)?.[1];
  const configured=[...cpuText.matchAll(/<VcDataObject\b[^>]*\bName=["']([^"']+)/gi)].map(match=>match[1]);
  const activeHmi=configured.find(name=>screenFolders.some(folder=>folder.toLowerCase()===name.toLowerCase()))||screenFolders[0];
  return {project_name:descriptor?.file.name.replace(/\.(apj|gdm)$/i,'')||first,automation_studio_version:version,active_configuration:active,plc_type:plcType,active_hmi:activeHmi,screen_folders:screenFolders,configured_hmi_objects:configured};
}

export function useCompareProjects(notify: Notify) {
  const [compareResult, setCompareResult] = useState<any | null>(null);
  const [compareProgress, setCompareProgress] = useState<any | null>(null);
  const [compareConsoleOpen, setCompareConsoleOpen] = useState(false);
  const [compareFiles, setCompareFiles] = useState<CompareFiles>({base: [], new_: []});
  const [compareBasePath, setCompareBasePath] = useState(() => {
    try { return userStorage.getItem('usopp_compare_base_path_v4.31') || ''; } catch { return ''; }
  });
  const [compareNewPath, setCompareNewPath] = useState(() => {
    try { return userStorage.getItem('usopp_compare_new_path_v4.31') || ''; } catch { return ''; }
  });
  const [compareBusy, setCompareBusy] = useState(false);
  const [baseProjectInfo,setBaseProjectInfo]=useState<ProjectInfo|null>(null);
  const [newProjectInfo,setNewProjectInfo]=useState<ProjectInfo|null>(null);
  const [baseHmi,setBaseHmi]=useState('');
  const [newHmi,setNewHmi]=useState('');

  useEffect(()=>{let cancelled=false;if(!compareBasePath){setBaseProjectInfo(null);return}fetch('/api/local/compare/project-info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_path:compareBasePath})}).then(r=>r.json()).then(info=>{if(!cancelled){setBaseProjectInfo(info);setBaseHmi(info.active_hmi||info.screen_folders?.[0]||'')}}).catch(()=>!cancelled&&setBaseProjectInfo(null));return()=>{cancelled=true}},[compareBasePath]);
  useEffect(()=>{let cancelled=false;if(!compareNewPath){setNewProjectInfo(null);return}fetch('/api/local/compare/project-info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_path:compareNewPath})}).then(r=>r.json()).then(info=>{if(!cancelled){setNewProjectInfo(info);setNewHmi(info.active_hmi||info.screen_folders?.[0]||'')}}).catch(()=>!cancelled&&setNewProjectInfo(null));return()=>{cancelled=true}},[compareNewPath]);
  useEffect(()=>{let cancelled=false;if(!compareFiles.base.length)return;inspectUploadedProject(compareFiles.base).then(info=>{if(!cancelled){setBaseProjectInfo(info);setBaseHmi(info?.active_hmi||info?.screen_folders?.[0]||'')}});return()=>{cancelled=true}},[compareFiles.base]);
  useEffect(()=>{let cancelled=false;if(!compareFiles.new_.length)return;inspectUploadedProject(compareFiles.new_).then(info=>{if(!cancelled){setNewProjectInfo(info);setNewHmi(info?.active_hmi||info?.screen_folders?.[0]||'')}});return()=>{cancelled=true}},[compareFiles.new_]);

  useEffect(()=>{userStorage.setItem('usopp_compare_base_path_v4.31',compareBasePath);userStorage.setItem('usopp_compare_new_path_v4.31',compareNewPath);setCompareResult(null);setCompareProgress(null)},[compareBasePath,compareNewPath,compareFiles,baseHmi,newHmi]);
  const runCompare = async () => {
    const localReady = Boolean(compareBasePath && compareNewPath);
    const uploadReady = compareFiles.base.length > 0 && compareFiles.new_.length > 0;
    if (!localReady && !uploadReady) {
      notify('Select both projects using local paths, or upload both project folders.');
      return;
    }
    setCompareBusy(true);
    setCompareResult(null);
    setCompareConsoleOpen(false);
    setCompareProgress({status:'starting',phase:'starting',percent:0,current:0,total:0,logs:['Starting comparison...']});
    try {
      if (localReady) {
        const response = await fetch('/api/local/compare/start', {
          method:'POST', headers:{'Content-Type':'application/json',...toolProjectHeaders('matchview')},
          body:JSON.stringify({base_path:compareBasePath,new_path:compareNewPath,base_hmi:baseHmi,new_hmi:newHmi})
        });
        const started = await response.json();
        if (!response.ok) throw new Error(started.detail || 'Could not start comparison');
        const sid = started.sessionId;
        let done = false;
        while (!done) {
          await new Promise(resolve => setTimeout(resolve, 500));
          const statusResponse = await fetch(`/api/local/compare/status/${sid}`);
          const status = await statusResponse.json();
          if (!statusResponse.ok) throw new Error(status.detail || 'Comparison status unavailable');
          setCompareProgress(status);
          if (status.status === 'complete') {
            setCompareResult(status.result);
            setCompareBusy(false);
            done = true;
            notify(`Comparison complete: ${status.result?.summary?.modified || 0} modified, ${status.result?.summary?.added || 0} added, ${status.result?.summary?.removed || 0} removed.`);
          } else if (status.status === 'error') {
            throw new Error(status.error || 'Comparison failed');
          }
        }
      } else {
        setCompareProgress((progress:any) => ({...progress,phase:'uploading/comparing',percent:0,logs:[...(progress?.logs || []),'Upload comparison started. Progress is available after the server completes the comparison.']}));
        const form = new FormData();
        const baseName = compareFiles.base[0]?.webkitRelativePath?.split('/')[0] || '';
        const newName = compareFiles.new_[0]?.webkitRelativePath?.split('/')[0] || '';
        const includeFile=(file:File)=>!file.webkitRelativePath.replace(/\\/g,'/').split('/').slice(1,-1).some(part=>['temp','as','binaries','diagnosis','.git','__pycache__'].includes(part.toLowerCase()));
        compareFiles.base.filter(includeFile).forEach(file => form.append('base_files',file,file.webkitRelativePath));
        compareFiles.new_.filter(includeFile).forEach(file => form.append('new_files',file,file.webkitRelativePath));
        form.append('base_name',baseName);
        form.append('new_name',newName);
        form.append('base_hmi',baseHmi);form.append('new_hmi',newHmi);
        const response = await fetch('/api/compare',{method:'POST',headers:toolProjectHeaders('matchview'),body:form});
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Compare failed');
        setCompareResult(result);
        setCompareProgress((progress:any) => ({status:'complete',phase:'complete',percent:100,logs:[...(progress?.logs || []),'Upload comparison complete.'],result}));
        notify(`Comparison complete: ${result.summary?.modified || 0} modified, ${result.summary?.added || 0} added, ${result.summary?.removed || 0} removed.`);
      }
    } catch (error:any) {
      setCompareProgress((progress:any) => ({...progress,status:'error',phase:'error',error:error.message || String(error),logs:[...(progress?.logs || []),`ERROR: ${error.message || String(error)}`]}));
      notify(error.message || 'Compare failed');
    } finally {
      setCompareBusy(false);
    }
  };

  return {
    result: compareResult,
    openHistory:(data:any)=>{setCompareResult(data);setCompareProgress(null)},
    compareFiles, setCompareFiles,
    compareBasePath, setCompareBasePath,
    compareNewPath, setCompareNewPath,
    baseProjectInfo,newProjectInfo,baseHmi,setBaseHmi,newHmi,setNewHmi,
    runCompare,
    busy: compareBusy,
    progress: compareProgress,
    consoleOpen: compareConsoleOpen,
    setConsoleOpen: setCompareConsoleOpen,
    clearResults:()=>{setCompareResult(null);setCompareProgress(null);setCompareConsoleOpen(false)}
  };
}
