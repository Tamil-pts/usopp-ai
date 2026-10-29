import {userStorage} from '../../shared/userStorage';
import {useEffect,useState} from 'react';
import {generateProjectMetadata,validateProject,prepareMetadata,type BoolMetadataMode} from './api';
import type {AnyResult} from '../../shared/types';
import {projectSourceFiles} from '../../shared/projectInput';
import {inferMachineDepartment,loadProjectDetails,type MachinePrefix,type ProjectDetails} from './projectDetails';

export function useValidationWorkspace(machinePrefixes:MachinePrefix[]) {
  const [projectFiles,setProjectFiles]=useState<File[]>([]);
  const [localProjectPath,setLocalProjectPath]=useState(()=>userStorage.getItem('usopp_project_path_v4.31')||'');
  const [localMetadataPath,setLocalMetadataPath]=useState(()=>userStorage.getItem('usopp_metadata_path_v4.31')||'');
  const [localMetadataName,setLocalMetadataName]=useState(()=>userStorage.getItem('usopp_metadata_name_v4.31')||'');
  const [projectName,setProjectName]=useState(()=>userStorage.getItem('usopp_project_name_v4.31')||'');
  const [machineDepartment,setMachineDepartmentState]=useState(()=>userStorage.getItem('usopp_machine_department_v1')||'All');
  const [departmentAutomatic,setDepartmentAutomatic]=useState(()=>userStorage.getItem('usopp_machine_department_auto_v1')!=='false');
  const [boolMetadataMode,setBoolMetadataModeState]=useState<BoolMetadataMode>(()=>userStorage.getItem('usopp_bool_metadata_mode_v1')==='USINT'?'USINT':'BOOL');
  const [metadata,setMetadata]=useState<File|null>(null);
  const [compareMetadata,setCompareMetadata]=useState(true);
  const [result,setResult]=useState<AnyResult|null>(null);
  const [generated,setGenerated]=useState<AnyResult|null>(null);
  const [sourceChanged,setSourceChanged]=useState(false);
  const [busy,setBusy]=useState('');
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [projectDetails,setProjectDetails]=useState<ProjectDetails|null>(null);
  const [detailsLoading,setDetailsLoading]=useState(false);
  const [detailsError,setDetailsError]=useState('');
  const [uploadProgress,setUploadProgress]=useState<{uploaded:number;total:number}|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    setProjectDetails(null);setDetailsError('');setDetailsLoading(false);
    if(!localProjectPath&&!projectFiles.length)return;
    setDetailsLoading(true);
    loadProjectDetails(localProjectPath,projectFiles,controller.signal)
      .then(details=>{if(!controller.signal.aborted)setProjectDetails(details)})
      .catch(e=>{if(!controller.signal.aborted)setDetailsError(e.message)})
      .finally(()=>{if(!controller.signal.aborted)setDetailsLoading(false)});
    return()=>controller.abort();
  },[localProjectPath,projectFiles]);
  useEffect(()=>{userStorage.setItem('usopp_project_path_v4.31',localProjectPath);userStorage.setItem('usopp_project_name_v4.31',projectName)},[localProjectPath,projectName]);
  useEffect(()=>{userStorage.setItem('usopp_machine_department_v1',machineDepartment);userStorage.setItem('usopp_machine_department_auto_v1',String(departmentAutomatic))},[machineDepartment,departmentAutomatic]);
  useEffect(()=>{userStorage.setItem('usopp_bool_metadata_mode_v1',boolMetadataMode)},[boolMetadataMode]);
  useEffect(()=>{if(departmentAutomatic&&projectDetails){setMachineDepartmentState(inferMachineDepartment(projectDetails.projectFiles,machinePrefixes))}},[departmentAutomatic,projectDetails,machinePrefixes]);
  useEffect(()=>{userStorage.setItem('usopp_metadata_path_v4.31',localMetadataPath);userStorage.setItem('usopp_metadata_name_v4.31',localMetadataName)},[localMetadataPath,localMetadataName]);
  const selectProject=(path:string,name:string,files:File[]=[])=>{setProjectDetails(null);setSourceChanged(false);setLocalProjectPath(path);setProjectFiles(files);setProjectName(name);setResult(null);setGenerated(null);setMessage('');setError('');setUploadProgress(null);setDepartmentAutomatic(true);setMachineDepartmentState(inferMachineDepartment(files.map(file=>file.name),machinePrefixes))};
  const setMachineDepartment=(value:string)=>{setDepartmentAutomatic(false);setMachineDepartmentState(value);setResult(null);setGenerated(null)};
  const setBoolMetadataMode=(value:BoolMetadataMode)=>{setBoolMetadataModeState(value);setResult(null);setGenerated(null);setMessage('');setError('')};
  const selectMetadata=(path:string,name:string)=>{setError('');setMetadata(null);setLocalMetadataPath(path);setLocalMetadataName(name);setResult(null)};
  const uploadMetadata=async(file:File)=>{setBusy('upload');setError('');setMessage('');try{const data=await prepareMetadata(file);selectMetadata(data.path,file.name);setMetadata(file);setMessage(`${file.name} is ready to view or validate.`)}catch(e:any){setError(e.message)}finally{setBusy('')}};
  const execute=async(kind:'validate'|'metadata',departmentOverride?:string)=>{
    if(!localProjectPath&&!projectFiles.length){setError('Select a project folder first.');return}
    const department=(departmentOverride??machineDepartment).trim();
    if(!department||department.toLowerCase()==='all'){setError('Select a machine / department before running validation or generating metadata.');return}
    setBusy(kind);setError('');setMessage('');setUploadProgress(projectFiles.length?{uploaded:0,total:projectSourceFiles(projectFiles).length}:null);
    try{
      const useMetadata=compareMetadata&&!!(localMetadataPath||metadata);
      const input={projectFiles,projectName,localProjectPath,localMetadataPath:useMetadata?localMetadataPath:'',metadata:useMetadata?metadata:null,machineDepartment:department,boolMetadataMode,onUploadProgress:(uploaded:number,total:number)=>setUploadProgress({uploaded,total})};
      if(kind==='validate'){setResult(await validateProject(input));setSourceChanged(false);setMessage(useMetadata?'Validation completed. Reports remain available in this session.':'Project validation completed without metadata. Metadata comparisons were skipped; reports remain available in this session.')}
      else {setGenerated(await generateProjectMetadata(input));setMessage('Metadata generated. Open Generated metadata to review, edit or export.')}
    }catch(e:any){setError(e.message||'Processing failed')}finally{setBusy('');setUploadProgress(null)}
  };
  return {projectFiles,localProjectPath,projectName,setProjectName,machineDepartment,setMachineDepartment,boolMetadataMode,setBoolMetadataMode,metadata,localMetadataPath,localMetadataName,
    compareMetadata,setCompareMetadata:(value:boolean)=>{setCompareMetadata(value);setResult(null)},
    sourceChanged,markSourceChanged:()=>{setSourceChanged(true);setGenerated(null)},
    setLocalMetadataPath,setLocalMetadataName,result,generated,busy,message,error,uploadProgress,projectDetails,detailsLoading,detailsError,selectProject,selectMetadata,uploadMetadata,
    runValidation:(department?:string)=>execute('validate',department),generateMetadata:(department?:string)=>execute('metadata',department),
    openHistory:(kind:string,data:any)=>{setLocalProjectPath('');setProjectFiles([]);setMetadata(null);setLocalMetadataPath('');setProjectName(data.projectName||'');setResult(kind==='validation'?data:null);setGenerated(kind==='metadata'?data:null);setSourceChanged(false);setError('');setMessage('Stored result opened. Use WorkHub history reuse actions to run this project again.');},
    adoptEditedProject:(path:string,name:string)=>{setLocalProjectPath(path);setProjectFiles([]);setProjectName(name);setResult(null);setGenerated(null);setSourceChanged(true)},
    clearResults:()=>{setResult(null);setGenerated(null);setSourceChanged(false)},clearProject:()=>selectProject('','')};
}
export type ValidationWorkspace=ReturnType<typeof useValidationWorkspace>;
