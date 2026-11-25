import {installNavigation} from './shared/navigation';
import './cryptoCompatibility';
import {createRoot} from 'react-dom/client';
import App from './app/App';
import {ReportExportProvider} from './shared/ReportExport';
import {AuthProvider} from './features/account/AuthProvider';
import {WorkspaceErrorBoundary} from './shared/WorkspaceErrorBoundary';

installNavigation();
if('serviceWorker'in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('/sw.js').catch(()=>{});});}
createRoot(document.getElementById('root')!).render(<WorkspaceErrorBoundary><AuthProvider><ReportExportProvider><App/></ReportExportProvider></AuthProvider></WorkspaceErrorBoundary>);
