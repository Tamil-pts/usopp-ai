import './cryptoCompatibility';
import './sessionCompatibility';
import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import {activateUserStorage} from '../../src/shared/userStorage';
import type {SavedInspectRun} from './utils/runHistory';

async function start() {
  const account = await fetch('/api/auth/session', {cache: 'no-store'});
  if (!account.ok) throw new Error('Sign in to uSOPp to use DataInspect.');
  const session = await account.json();
  if (!session.user) throw new Error('Sign in to uSOPp to use DataInspect.');
  activateUserStorage(session.user);
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
  createRoot(document.getElementById('root')!).render(<StrictMode><App initialHistory={initialHistory}/></StrictMode>);
}
void start().catch(error => {
  const message = document.createElement('p');
  message.textContent = error instanceof Error ? error.message : 'DataInspect could not be loaded.';
  message.style.padding = '24px';
  document.getElementById('root')!.replaceChildren(message);
});
