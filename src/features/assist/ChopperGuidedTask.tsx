/**
 * ChopperGuidedTask
 *
 * Conversational task creation inside the Chopper quick-help panel.
 * Chopper asks one question at a time, collects answers, then passes
 * the brief + prefill to startAssistantTask() to open the right workspace
 * with all fields pre-populated.
 *
 * Usage:
 *   <ChopperGuidedTask taskId="project" onDone={close} onCancel={...} modules={modules} />
 */
import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Check,ChevronLeft,Loader,RotateCcw,X} from 'lucide-react';
import {assistantTasks,startAssistantTask} from './taskActions';
import type {WorkspaceModule} from '../../shared/workspaceModules';

// ─── Types ───────────────────────────────────────────────────────────────────

export type GuidedTaskId = 'project'|'frd'|'mom'|'task'|'fat'|'closure'|'test';

type Question = {
  key: string;
  q: string;
  placeholder?: string;
  multiline?: boolean;
  optional?: boolean;
};

type Script = {
  label: string;
  destination: string;
  intro: string;
  questions: Question[];
};

type Answers = Record<string, string>;

// ─── Script cache (fetched once per session) ─────────────────────────────────

const scriptCache: Record<string, Script> = {};

async function loadScript(taskId: string): Promise<Script> {
  if (scriptCache[taskId]) return scriptCache[taskId];
  const r = await fetch(`/api/assist/guided-task/${taskId}`);
  if (!r.ok) throw new Error(`Could not load task script for '${taskId}'.`);
  const data: Script = await r.json();
  scriptCache[taskId] = data;
  return data;
}

async function buildBrief(taskId: string, answers: Answers): Promise<{brief: string; prefill: Record<string,unknown>; destination: string}> {
  const r = await fetch(`/api/assist/guided-task/${taskId}/brief`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({answers}),
  });
  if (!r.ok) {
    const err = await r.json().catch(()=>({detail:'Failed to build task brief.'}));
    throw new Error(err.detail || 'Failed to build task brief.');
  }
  return r.json();
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ChopperGuidedTask({
  taskId,
  modules,
  onDone,
  onCancel,
}: {
  taskId: GuidedTaskId;
  modules: WorkspaceModule[];
  onDone: (message: string) => void;
  onCancel: () => void;
}) {
  const [script, setScript] = useState<Script|null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [step, setStep] = useState(0);           // current question index
  const [answers, setAnswers] = useState<Answers>({});
  const [current, setCurrent] = useState('');     // text in the active input
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load script on mount
  useEffect(() => {
    setLoading(true);
    loadScript(taskId)
      .then(s => { setScript(s); setLoading(false); })
      .catch(e => { setError((e as Error).message); setLoading(false); });
  }, [taskId]);

  // Auto-focus input when step changes
  useEffect(() => {
    if (!loading && !done) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [step, loading, done]);

  if (loading) {
    return (
      <div className="chopperGuidedTask" role="status">
        <Loader size={16} className="spin"/>
        <span>Loading task questions…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="chopperGuidedTask">
        <p className="chopperGuidedError" role="alert">{error}</p>
        <button className="btn" onClick={onCancel}><X size={14}/> Cancel</button>
      </div>
    );
  }

  if (!script) return null;

  const questions = script.questions;
  const q = questions[step];
  const totalRequired = questions.filter(x => !x.optional).length;
  const answeredRequired = questions.filter(x => !x.optional && answers[x.key]?.trim()).length;
  const isLast = step === questions.length - 1;

  async function advance() {
    if (busy) return;
    const value = current.trim();

    // Validate required
    if (!value && !q.optional) {
      setError(`Please answer: ${q.q}`);
      return;
    }
    setError('');

    // Store answer (even blank for optional)
    const nextAnswers = { ...answers, [q.key]: value };
    setAnswers(nextAnswers);
    setCurrent('');

    if (!isLast) {
      setStep(s => s + 1);
      return;
    }

    // All questions answered — build brief and launch task
    setBusy(true);
    try {
      const { brief, prefill, destination } = await buildBrief(taskId, nextAnswers);

      // Find the matching AssistantTask by destination id
      const matchTask = assistantTasks.find(t => t.id === destination || t.id === taskId);
      if (!matchTask) {
        throw new Error(`No Chopper task registered for '${destination}'. Open WorkHub manually.`);
      }

      // Store the prefill in sessionStorage so the destination form can read it
      try {
        sessionStorage.setItem('usopp_chopper_prefill', JSON.stringify({ taskId, prefill, ts: Date.now() }));
      } catch { /* storage quota */ }

      // Navigate and pass the brief text
      const launched = startAssistantTask(matchTask, modules, brief);
      if (!launched) throw new Error('This workspace is not available for your account.');

      setDone(true);
      onDone(`Opening **${script?.label || 'task'}** with your answers pre-filled. Review and confirm in the workspace.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function skip() {
    if (q.optional) {
      setAnswers(prev => ({ ...prev, [q.key]: '' }));
      setCurrent('');
      setError('');
      if (isLast) { void advance(); } else { setStep(s => s + 1); }
    }
  }

  function back() {
    if (step > 0) {
      setCurrent(answers[questions[step-1].key] || '');
      setStep(s => s - 1);
      setError('');
    }
  }

  function reset() {
    setStep(0);
    setAnswers({});
    setCurrent('');
    setError('');
    setDone(false);
  }

  if (done) {
    return (
      <div className="chopperGuidedTask chopperGuidedDone">
        <Check size={20}/>
        <p><strong>{script.label}</strong> opened with your answers pre-filled.</p>
        <div className="chopperGuidedActions">
          <button className="btn" onClick={reset}><RotateCcw size={13}/> Start over</button>
          <button className="btn" onClick={onCancel}><X size={13}/> Close</button>
        </div>
      </div>
    );
  }

  // Progress bar: answered required questions / total required
  const progress = totalRequired > 0 ? Math.round((answeredRequired / totalRequired) * 100) : 0;

  return (
    <div className="chopperGuidedTask">
      {/* Header */}
      <div className="chopperGuidedHeader">
        <strong>{script.label}</strong>
        <button className="btn" aria-label="Cancel guided task" onClick={onCancel}><X size={14}/></button>
      </div>

      {/* Intro on first step */}
      {step === 0 && (
        <p className="chopperGuidedIntro">{script.intro}</p>
      )}

      {/* Progress */}
      <div className="chopperGuidedProgress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <div className="chopperGuidedProgressBar" style={{width: progress+'%'}}/>
        <span>Question {step+1} of {questions.length}{q.optional ? ' (optional)' : ''}</span>
      </div>

      {/* Previous answers summary */}
      {step > 0 && (
        <div className="chopperGuidedHistory">
          {questions.slice(0, step).map((prev, i) => {
            const ans = answers[prev.key];
            if (!ans) return null;
            return (
              <div key={i} className="chopperGuidedPrev">
                <small>{prev.q}</small>
                <span>{ans.length > 80 ? ans.slice(0, 80) + '…' : ans}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Current question */}
      <div className="chopperGuidedQuestion">
        <label htmlFor="chopper-guided-input">
          {q.q}
          {q.optional && <small className="chopperGuidedOptional"> (optional — press Skip)</small>}
        </label>
        <textarea
          ref={inputRef}
          id="chopper-guided-input"
          className="textInput"
          rows={q.multiline ? 4 : 2}
          maxLength={4000}
          placeholder={q.placeholder || ''}
          value={current}
          disabled={busy}
          onChange={e => { setCurrent(e.target.value); setError(''); }}
          onKeyDown={e => {
            // Enter submits unless multiline (Shift+Enter = newline in multiline)
            if (e.key === 'Enter' && !e.shiftKey && !q.multiline && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void advance();
            }
          }}
        />
      </div>

      {error && <p className="chopperGuidedError" role="alert">{error}</p>}

      {/* Actions */}
      <div className="chopperGuidedActions">
        {step > 0 && (
          <button className="btn" disabled={busy} onClick={back}>
            <ChevronLeft size={14}/> Back
          </button>
        )}
        {q.optional && (
          <button className="btn" disabled={busy} onClick={skip}>
            Skip
          </button>
        )}
        <button
          className="btn primary"
          disabled={busy || (!current.trim() && !q.optional)}
          onClick={() => void advance()}
        >
          {busy
            ? <><Loader size={14} className="spin"/> Working…</>
            : isLast
              ? <><Check size={14}/> {script.label}</>
              : <>Next <ArrowRight size={14}/></>
          }
        </button>
      </div>
    </div>
  );
}

/**
 * Utility: read the prefill that ChopperGuidedTask stored in sessionStorage.
 * Call this inside the target workspace (FRD editor, project dialog, etc.)
 * on mount to auto-populate fields.
 *
 * @param taskId  Expected task type (e.g. 'project', 'frd').
 * @param maxAgeMs  Max age in ms (default 5 minutes).
 */
export function readChopperPrefill(taskId?: string, maxAgeMs = 5 * 60 * 1000): Record<string,unknown>|null {
  try {
    const raw = sessionStorage.getItem('usopp_chopper_prefill');
    if (!raw) return null;
    const { taskId: storedTask, prefill, ts } = JSON.parse(raw) as { taskId: string; prefill: Record<string,unknown>; ts: number };
    if (taskId && storedTask !== taskId) return null;
    if (Date.now() - ts > maxAgeMs) { sessionStorage.removeItem('usopp_chopper_prefill'); return null; }
    return prefill;
  } catch { return null; }
}
