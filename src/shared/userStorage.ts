/** Synchronous UI cache backed by authenticated, revision-checked server storage. */
type User = {id: number; role?: string};
type Entry = {value: string | null; revision: number};
type Change = Entry & {key: string};
let accountId: number | null = null;
let entries: Record<string, Entry> = {};
let pending: Record<string, Change> = {};
let saving = false;
let problem = '';
let timer: ReturnType<typeof setTimeout> | undefined;
const allowed = /^(usopp_|spinning_|spinconnect_|nami_)|^plc_configs$/;
// The main workspace and DataInspect keep separate retry journals in each tab.
const windowStorageId = (() => {
  const key = `usopp-storage-window:${location.pathname}`;
  const fresh = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  try {const saved = sessionStorage.getItem(key);if (saved) return saved;sessionStorage.setItem(key, fresh);} catch {/* Server storage works without sessionStorage. */}
  return fresh;
})();
const prefix = (id = accountId) => `usopp-user:${id ?? 'signed-out'}:`;
const journalKey = (id = accountId) => `usopp-pending:${id}:${windowStorageId}`;
const cached = (key: string) => {try {return localStorage.getItem(prefix() + key);} catch {return null;}};
const mirror = (key: string, value: string | null) => {
  try {if (value === null) localStorage.removeItem(prefix() + key); else localStorage.setItem(prefix() + key, value);} catch {/* Server still saves when browser quota is full. */}
};
const announce = () => window.dispatchEvent(new Event('usopp-storage-status'));
const canAutosave = () => !problem || problem.startsWith('Browser backup is full.');
const journal = () => {
  if (!Object.keys(pending).length) {try {localStorage.removeItem(journalKey());} catch {/* There are no unsaved changes. */}return;}
  try {localStorage.setItem(journalKey(), JSON.stringify(pending));} catch {
    problem = 'Browser backup is full. Keep this window open until settings finish saving to the server.';
  }
};

async function request(changes?: Change[], importMissing = false, id = accountId) {
  const response = await fetch('/api/account/storage', {credentials: 'same-origin', cache: 'no-store',
    ...(changes ? {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({accountId: id, changes, importMissing})} : {})});
  let data: {accountId: number; entries: Record<string, Entry>; detail?: string};
  try {data = await response.json();} catch {throw new Error('Server storage is unavailable. Restart the updated uSOPp server.');}
  if (!response.ok) throw new Error(data.detail || 'Could not save settings to the server.');
  if (data.accountId !== id || !data.entries) throw new Error('The saved-settings account changed. Sign in again.');
  return data.entries;
}

export function activateUserStorage(user: User | null) {
  if (timer) clearTimeout(timer);
  accountId = user?.id ?? null;
  entries = {}; pending = {}; problem = '';
  if (user?.role === 'admin' && !cached('storage-migrated-v1')) {
    try {
      for (const key of Object.keys(localStorage).filter(key => allowed.test(key))) {
        if (cached(key) === null) mirror(key, localStorage.getItem(key));
      }
      mirror('storage-migrated-v1', '1');
    } catch {/* Existing server records take priority over browser migration. */}
  }
  announce();
}

export async function hydrateUserStorage(user: User) {
  activateUserStorage(user);
  const id = user.id;
  let server = await request(undefined, false, id);
  // Adopt surviving browser-only settings once. Tombstones prevent resurrection.
  const migration: Change[] = [];
  try {
    for (const scoped of Object.keys(localStorage).filter(key => key.startsWith(prefix(id)))) {
      const key = scoped.slice(prefix(id).length);
      if (allowed.test(key) && !(key in server)) migration.push({key, value: localStorage.getItem(scoped), revision: 0});
    }
  } catch {/* A new browser loads the same server settings without local storage. */}
  let batch: Change[] = [], bytes = 0;
  for (const item of migration) {
    const size = new Blob([item.value || '']).size;
    if (size > 8 * 1024 * 1024) {problem = 'One browser setting exceeds 8 MB; import its metadata as a file.'; continue;}
    if (batch.length >= 100 || bytes + size > 8 * 1024 * 1024) {server = await request(batch, true, id); batch = []; bytes = 0;}
    batch.push(item); bytes += size;
  }
  if (batch.length) server = await request(batch, true, id);
  if (accountId !== id) return;
  entries = server;
  for (const [key, entry] of Object.entries(server)) mirror(key, entry.value);
  try {const saved = JSON.parse(localStorage.getItem(journalKey(id)) || '{}');pending = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};} catch {pending = {};}
  for (const [key, change] of Object.entries(pending)) {
    if (!allowed.test(key) || typeof change !== 'object' || change === null || change.key !== key || (change.value !== null && typeof change.value !== 'string') || !Number.isInteger(change.revision) || change.revision < 0) {delete pending[key]; continue;}
    if (server[key]?.value === change.value) {delete pending[key]; continue;}
    if ((server[key]?.revision || 0) !== change.revision) {
      problem = 'Some unsaved settings conflict with the server copy. Download your unsaved settings, then reload server settings.';
    } else {entries[key] = {value: change.value, revision: change.revision}; mirror(key, change.value);}
  }
  journal(); announce();
  if (canAutosave() && Object.keys(pending).length) void flushUserStorage();
}

export async function flushUserStorage() {
  if (saving || accountId === null || !Object.keys(pending).length) return;
  const id = accountId;
  saving = true; announce();
  try {
    while (accountId === id && Object.keys(pending).length) {
      const batch: Change[] = []; let bytes = 0;
      for (const item of Object.values(pending)) {
        const size = new Blob([item.value || '']).size;
        if (batch.length && (batch.length >= 100 || bytes + size > 8 * 1024 * 1024)) break;
        batch.push({...item}); bytes += size;
      }
      const server = await request(batch, false, id);
      if (accountId !== id) break;
      for (const item of batch) {
        const current = pending[item.key]; const stored = server[item.key];
        if (!stored) throw new Error('Server did not retain the saved setting.');
        if (current?.value === item.value) {delete pending[item.key]; entries[item.key] = stored;}
        else if (current) {current.revision = stored.revision; entries[item.key].revision = stored.revision;}
      }
      problem = ''; journal(); announce();
    }
  } catch (error) {
    if (accountId === id) problem = error instanceof Error ? error.message : 'Could not save settings. Retry when the server is reachable.';
  } finally {
    saving = false; announce();
    if (accountId !== id && Object.keys(pending).length) void flushUserStorage();
  }
}

export function storageStatus() {return {saving, pending: Object.keys(pending).length, error: problem};}
export function downloadUnsavedSettings() {
  const url = URL.createObjectURL(new Blob([JSON.stringify({accountId, changes: Object.values(pending)}, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = `usopp-unsaved-settings-${accountId}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function reloadServerSettings() {
  if (saving) return;
  try {
    if (Object.keys(pending).length) localStorage.setItem(`usopp-recovery:${accountId}:${Date.now()}`, JSON.stringify(pending));
    localStorage.removeItem(journalKey()); location.reload();
  } catch {problem = 'Download unsaved settings first; browser recovery storage is full.'; announce();}
}

export const userStorage = {
  getItem: (key: string) => key in entries ? entries[key].value : cached(key),
  setItem: (key: string, value: string) => {
    if ((key in entries ? entries[key].value : cached(key)) === value) return;
    const revision = entries[key]?.revision || 0;
    entries[key] = {value, revision}; mirror(key, value);
    if (accountId !== null && allowed.test(key)) {
      pending[key] = {key, value, revision: pending[key]?.revision ?? revision}; journal(); announce();
      if (timer) clearTimeout(timer); timer = setTimeout(() => {if (canAutosave()) void flushUserStorage();}, 200);
    }
  },
  removeItem: (key: string) => {
    const revision = entries[key]?.revision || 0;
    entries[key] = {value: null, revision}; mirror(key, null);
    if (accountId !== null && allowed.test(key)) {
      pending[key] = {key, value: null, revision: pending[key]?.revision ?? revision}; journal(); announce();
      if (canAutosave()) void flushUserStorage();
    }
  },
  clear: () => Object.keys(entries).forEach(key => userStorage.removeItem(key)),
};
window.addEventListener('online', () => void flushUserStorage());
window.addEventListener('visibilitychange', () => {if (document.visibilityState === 'hidden') void flushUserStorage();});
