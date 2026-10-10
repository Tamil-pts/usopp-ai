import './cryptoCompatibility';
import {createRoot} from 'react-dom/client';
import App from './app/App';
import {ReportExportProvider} from './shared/ReportExport';
import {AuthProvider} from './features/account/AuthProvider';

createRoot(document.getElementById('root')!).render(<AuthProvider><ReportExportProvider><App/></ReportExportProvider></AuthProvider>);
