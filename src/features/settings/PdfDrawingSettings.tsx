import {useEffect,useState} from 'react';
import {FileText,Save,CheckCircle2,Sparkles} from 'lucide-react';

interface PdfLimits {
  version: string;
  maxPages: number;
  maxFileSizeMB: number;
}

const PAGE_PRESETS = [
  {label: '1,000 pages', value: 1000},
  {label: '5,000 pages', value: 5000},
  {label: '10,000 pages (Default)', value: 10000},
  {label: '25,000 pages', value: 25000},
  {label: '100,000 pages (Unlimited)', value: 100000},
];

const SIZE_PRESETS = [
  {label: '100 MB', value: 100},
  {label: '300 MB', value: 300},
  {label: '500 MB (Default)', value: 500},
  {label: '1 GB (1,024 MB)', value: 1024},
  {label: '2 GB (2,048 MB)', value: 2048},
];

export function PdfDrawingSettings() {
  const [limits, setLimits] = useState<PdfLimits>({version: '1.0', maxPages: 10000, maxFileSizeMB: 500});
  const [pagesInput, setPagesInput] = useState('10000');
  const [sizeInput, setSizeInput] = useState('500');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/admin/settings/pdf-drawing-limits', {cache: 'no-store'})
      .then(async r => {
        const data = await r.json();
        if (r.ok && typeof data.maxPages === 'number') {
          setLimits(data);
          setPagesInput(String(data.maxPages));
          setSizeInput(String(data.maxFileSizeMB || 500));
        }
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    setBusy(true);
    setError('');
    setMessage('');
    const pages = parseInt(pagesInput, 10);
    const size = parseInt(sizeInput, 10);
    if (isNaN(pages) || pages < 1 || pages > 100000) {
      setError('Enter a page limit between 1 and 100,000.');
      setBusy(false);
      return;
    }
    if (isNaN(size) || size < 10 || size > 2048) {
      setError('Enter a file size limit between 10 and 2,048 MB.');
      setBusy(false);
      return;
    }

    try {
      const response = await fetch('/api/admin/settings/pdf-drawing-limits', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({maxPages: pages, maxFileSizeMB: size}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not save PDF limits.');
      setLimits(data);
      setMessage(`PDF upload limit successfully updated to ${data.maxPages.toLocaleString()} pages (${data.maxFileSizeMB} MB).`);
    } catch (e: any) {
      setError(e.message || 'Failed to save settings.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card setting wide">
      <div className="widgetHead">
        <h3><FileText size={18} style={{marginRight: 6, verticalAlign: 'text-bottom'}}/>PDF Drawing & Electrical Compare Limits</h3>
        <button className="btn primary" disabled={busy} onClick={() => void save()}>
          <Save size={13}/>Save PDF limits
        </button>
      </div>
      <p>
        Controls the maximum page count and file size allowed when uploading electrical circuit drawings (MatchView Circuit Compare),
        PLC PDF network prints, and e-design review schematics.
      </p>

      <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', margin: '14px 0'}}>
        <div>
          <label style={{fontWeight: 600, display: 'block', marginBottom: 6}}>
            Maximum drawing pages:
          </label>
          <input
            type="number"
            className="textInput"
            min={1}
            max={100000}
            value={pagesInput}
            disabled={busy}
            onChange={e => setPagesInput(e.target.value)}
            style={{width: '100%', marginBottom: 8}}
          />
          <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px'}}>
            {PAGE_PRESETS.map(p => (
              <button
                key={p.value}
                type="button"
                className={`chip ${parseInt(pagesInput, 10) === p.value ? 'active' : ''}`}
                onClick={() => setPagesInput(String(p.value))}
                disabled={busy}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label style={{fontWeight: 600, display: 'block', marginBottom: 6}}>
            Maximum file size (MB):
          </label>
          <input
            type="number"
            className="textInput"
            min={10}
            max={2048}
            value={sizeInput}
            disabled={busy}
            onChange={e => setSizeInput(e.target.value)}
            style={{width: '100%', marginBottom: 8}}
          />
          <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px'}}>
            {SIZE_PRESETS.map(s => (
              <button
                key={s.value}
                type="button"
                className={`chip ${parseInt(sizeInput, 10) === s.value ? 'active' : ''}`}
                onClick={() => setSizeInput(String(s.value))}
                disabled={busy}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="boolModeCurrent" style={{marginTop: 12}}>
        Active drawing contract: <b>Up to {limits.maxPages.toLocaleString()} pages · {limits.maxFileSizeMB} MB per file</b>
        <span style={{display: 'block', fontSize: '11px', color: 'var(--muted, #63798b)', marginTop: 4}}>
          Applies instantly to MatchView Circuit Compare, e-design Drawing Review, and PLC PDF comparison without restarting the server.
        </span>
      </div>

      {message && <p role="status" style={{color: '#159447', marginTop: 10}}><CheckCircle2 size={14} style={{verticalAlign: 'text-bottom', marginRight: 4}}/>{message}</p>}
      {error && <p role="alert" style={{color: '#d43f4d', marginTop: 10}}>{error}</p>}
    </section>
  );
}
