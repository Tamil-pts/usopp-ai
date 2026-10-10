import {FolderOpen,FileSpreadsheet} from 'lucide-react';
import type {ValidationWorkspace} from './useValidationWorkspace';
import type {ReactNode} from 'react';

export function ProjectSummary({workspace:w,onViewMetadata,projectControls,metadataControls}:{workspace:ValidationWorkspace;onViewMetadata:()=>void;projectControls?:ReactNode;metadataControls?:ReactNode}) {
  const hasProject=!!w.localProjectPath||w.projectFiles.length>0;
  const metadataName=w.localMetadataName||w.metadata?.name||w.localMetadataPath.split(/[\\/]/).pop();
  return <div className="validationSelection" aria-label="Selected validation inputs">
    <section className="card selectionCard selectionProjectCard">
      <div className="selectionIdentity">
      <div className="selectionHeading"><FolderOpen size={20}/><span>Selected project</span>{hasProject&&<span className="selectionMode">{w.localProjectPath?'Local folder':`${w.projectFiles.length.toLocaleString()} selected files`}</span>}</div>
      <strong className="selectionName">{hasProject?(w.projectName||w.projectDetails?.projectName||'Selected project'):'No project selected'}</strong>
      {!!w.projectDetails?.projectFiles.length&&<div className="selectionProjectFile">{w.projectDetails.projectFiles.join(', ')}</div>}
      {hasProject&&!projectControls&&<div className="selectionPath">{w.localProjectPath||w.projectDetails?.projectPath||w.projectFiles[0]?.webkitRelativePath.split('/')[0]}</div>}
      </div>
      {hasProject&&w.projectDetails&&<div className="projectFacts">
        <span><b>Automation Studio</b>{w.projectDetails.automationStudioVersion||'Not detected'}</span>
        <span><b>Active configuration</b>{w.projectDetails.activeConfiguration||'Not detected'}</span>
        <span><b>PLC type</b>{w.projectDetails.plcType||'Not detected'}</span>
        <span><b>Screen folder</b>{w.projectDetails.screenFolder||'Not detected'}</span>
        {w.projectDetails.screenType&&<span title={w.projectDetails.screenHardwareFile||undefined}><b>HMI type</b>{w.projectDetails.screenType}</span>}
        {w.projectDetails.legacyCpuRoot&&<span><b>PLC sources</b>{w.projectDetails.legacyCpuRoot}</span>}
      </div>}
      {w.projectDetails?.logicScopeMessage&&<p className="selectionHint">{w.projectDetails.logicScopeMessage}</p>}
      {projectControls}
    </section>
    <section className="card selectionCard">
      <div className="selectionHeading"><FileSpreadsheet size={20}/><span>Metadata file (optional)</span>{w.metadata&&<span className="selectionMode">Uploaded workbook</span>}</div>
      <p className="selectionHint">Run validation with the project alone. A metadata workbook is only needed for metadata comparisons.</p>
      {!!(w.localMetadataPath||w.metadata)&&<label><input type="checkbox" checked={w.compareMetadata} disabled={!!w.busy} onChange={event=>w.setCompareMetadata(event.target.checked)}/> Compare with selected metadata workbook</label>}
      <strong className="selectionName">{metadataName||'No metadata selected'}</strong>
      {w.localMetadataPath?<>{!metadataControls&&<div className="selectionPath">{w.localMetadataPath}</div>}<button className="btn selectionView" onClick={onViewMetadata}>View / edit metadata</button></>:
        <p className="selectionHint">No workbook selected. Metadata comparisons will be skipped.</p>}
      {metadataControls}
    </section>
  </div>;
}
