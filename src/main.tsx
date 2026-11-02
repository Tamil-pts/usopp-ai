import './cryptoCompatibility';
import {createRoot} from 'react-dom/client';
import App from './app/App';
import {ReportExportProvider} from './shared/ReportExport';
import {AuthProvider} from './features/account/AuthProvider';
import {WorkspaceErrorBoundary} from './shared/WorkspaceErrorBoundary';

createRoot(document.getElementById('root')!).render(<WorkspaceErrorBoundary><AuthProvider><ReportExportProvider><App/></ReportExportProvider></AuthProvider></WorkspaceErrorBoundary>);
