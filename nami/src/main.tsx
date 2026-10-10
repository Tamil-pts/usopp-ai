import './cryptoCompatibility';
import './sessionCompatibility';
import {Component, StrictMode, type ErrorInfo, type ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import {hydrateUserStorage} from '../../src/shared/userStorage';
import {StorageNotice} from '../../src/shared/StorageNotice';
import type {SavedInspectRun} from './utils/runHistory';

class DataInspectBoundary extends Component<{children: ReactNode}, {error: Error | null}> {
  state = {error: null as Error | null};
  static getDerivedStateFromError(error: Error) {return {error};}
  componentDidCatch(error: Error, info: ErrorInfo) {console.error('DataInspect could not render:', error, info.componentStack);}
  render() {
    if (!this.state.error) return this.props.children;
    return <section role="alert" className="di-startup-error">
      <h1>DataInspect could not open</h1>
      <p>Reload DataInspect to try again. Your saved targets, metadata and results are retained.</p>
      <details><summary>Error details</summary><pre>{this.state.error.message}</pre></details>
      <button type="button" onClick={() => location.reload()}>Reload DataInspect</button>
    </section>;
  }
}

async function start() {
  const account = await fetch('/api/auth/session', {cache: 'no-store'});
  if (!account.ok) throw new Error('Sign in to uSOPp to use DataInspect.');
  const session = await account.json();
  if (!session.user) throw new Error('Sign in to uSOPp to use DataInspect.');
  await hydrateUserStorage(session.user);
  await import('./theme');
  const historyId = new URLSearchParams(location.search).get('historyId');
  let initialHistory: SavedInspectRun | undefined;
  if (historyId) {
    const response = await fetch(`/api/history/${encodeURIComponent(historyId)}`);
    if (!response.ok) throw new Error('This saved test is unavailable or belongs to another user.');
    const saved = await response.json();
    if (saved.record.kind !== 'datainspect') throw new Error('This is not a DataInspect test.');
    initialHistory = saved.result;
  }
  createRoot(document.getElementById('root')!).render(<StrictMode><DataInspectBoundary><App initialHistory={initialHistory}/><StorageNotice/></DataInspectBoundary></StrictMode>);
}
void start().catch(error => {
  const message = document.createElement('p');
  message.textContent = error instanceof Error ? error.message : 'DataInspect could not be loaded.';
  message.style.padding = '24px';
  document.getElementById('root')!.replaceChildren(message);
});
