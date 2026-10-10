import {useEffect, useState} from 'react';
import {storageStatus, flushUserStorage, downloadUnsavedSettings, reloadServerSettings} from './userStorage';

export function StorageNotice() {
  const [status, setStatus] = useState(storageStatus);
  useEffect(() => {
    const update = () => setStatus(storageStatus());
    window.addEventListener('usopp-storage-status', update);
    return () => window.removeEventListener('usopp-storage-status', update);
  }, []);
  if (!status.pending && !status.error) return null;
  return <div role={status.error ? 'alert' : 'status'} style={{position: 'fixed', bottom: 16, right: 16, zIndex: 10000, maxWidth: 520, padding: '12px 16px', background: '#073B4C', color: '#fff', borderRadius: 8, boxShadow: '0 3px 16px #0003'}}>
    {status.error || 'Saving settings to the server…'}
    {status.error && <div style={{display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap'}}>
      <button disabled={status.saving} onClick={() => void flushUserStorage()}>Retry save</button>
      <button onClick={downloadUnsavedSettings}>Download unsaved settings</button>
      <button disabled={status.saving} onClick={() => void reloadServerSettings()}>Reload server settings</button>
    </div>}
  </div>;
}
