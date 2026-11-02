import {Component,type ErrorInfo,type ReactNode} from 'react';
import {AlertTriangle,RefreshCw} from 'lucide-react';
import './workspace-error.css';

export class WorkspaceErrorBoundary extends Component<{children:ReactNode},{error:Error|null}>{
 state:{error:Error|null}={error:null};
 static getDerivedStateFromError(error:Error){return {error};}
 componentDidCatch(error:Error,info:ErrorInfo){console.error('Workspace page error:',error,info.componentStack);}
 render(){if(!this.state.error)return this.props.children;const message=this.state.error.message||'Unknown page error',asset=/fetch dynamically imported module|loading chunk|importing a module|module script|preload/i.test(message);return <main className="workspaceLoadError" role="alert"><section><AlertTriangle size={30}/><h1>{asset?'Load the updated interface':'This page could not open'}</h1><p>{asset?'This tab is using files from an earlier interface build. Reload to open the current pages.':'An unexpected page error occurred. Reload the interface to try again.'}</p><button className="btn primary" onClick={()=>{const url=new URL(location.href);url.searchParams.set('usopp_reload',String(Date.now()));location.replace(url.href);}}><RefreshCw size={16}/>Reload interface</button><details><summary>Error details</summary><pre>{message}</pre></details></section></main>;}
}
