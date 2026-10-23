import packageInfo from '../../package.json';

export type AppHealth={version:string;status?:string;frontendBuild?:{version:string|null;matches:boolean;error?:string|null}};
export function updatedInterfaceUrl(current:string,version:string,now=Date.now()){
 const url=new URL(current);url.searchParams.set('usopp_build',`${version}-${now}`);return url.href;
}
export function BuildVersionBadge({health}:{health:AppHealth|null}){
 const matches=!!health&&health.version===packageInfo.version&&health.status!=='version-mismatch';
 return <span className={'badge '+(matches?'pass':'warn')}>{health?`UI ${packageInfo.version} | API ${health.version}`:'API unavailable — check launcher logs'}</span>;
}
export function BuildVersionNotice({health}:{health:AppHealth|null}){
 if(!health)return null;
 if(health.status==='version-mismatch')return <div className="ruleMessage" role="alert">The server interface build does not match this API release. Install the matching container or rebuild the interface. {health.frontendBuild?.error}</div>;
 if(health.version===packageInfo.version)return null;
 return <div className="ruleMessage" role="status">A newer interface is available. Save any edits, then <button className="btn" onClick={()=>window.location.replace(updatedInterfaceUrl(window.location.href,health.version))}>Reload interface</button></div>;
}
