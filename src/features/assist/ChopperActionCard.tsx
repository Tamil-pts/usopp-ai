import React from 'react';
import {CheckCircle2, AlertTriangle, XCircle, ArrowRight, RefreshCw, FileText, ExternalLink, Play, Ban, FolderUp, FileUp, Clock} from 'lucide-react';
import {navigateRoute} from '../../shared/navigation';
import './chopper-action-card.css';

export interface ChopperActionCardProps {
  card: {
    type: 'action-question' | 'action-plan' | 'action-summary' | 'action-error' | 'action-cancelled';
    actionId?: string;
    actionTitle?: string;
    description?: string;
    question?: string;
    slot?: string;
    slotKind?: string;
    label?: string;
    choices?: string[];
    optional?: boolean;
    notice?: string;
    message?: string;
    slotSummary?: Array<{label: string; value: string}>;
    counts?: {fail: number; warning: number; pass: number; error: number; groups: number};
    topFails?: Array<{severity: string; parameter: string; message: string; location?: string}>;
    topWarnings?: Array<{severity: string; parameter: string; message: string; location?: string}>;
    summary?: {added: number; removed: number; modified: number; unchanged: number};
    byCategory?: Record<string, number>;
    topChanged?: Array<{path: string; category: string; status: string}>;
    projectName?: string;
    projectId?: string;
    scopeId?: string;
    docTitle?: string;
    documentNumber?: string;
    meetingSubject?: string;
    scope?: string;
    testScope?: string;
    acceptanceCriteria?: string;
    customer?: string;
    department?: string;
    documents?: Array<{kind: string; title: string; status: string}>;
    requirements?: Array<{id?: string; title?: string; description?: string}>;
    decisions?: Array<{decision?: string; owner?: string}>;
    actions?: Array<{task?: string; owner?: string}>;
    cases?: Array<{id?: string; title?: string; expected?: string}>;
    score?: number;
    deepLink?: {page: string; sessionId?: string; projectId?: string; scopeId?: string};
  };
  onAnswer: (text: string) => void;
  onOpenFeature?: (feature: string) => void;
  onUploadFolder?: () => void;
  onUploadFile?: () => void;
  disabled?: boolean;
}

export function ChopperActionCard({card, onAnswer, onOpenFeature, onUploadFolder, onUploadFile, disabled}: ChopperActionCardProps) {
  if (card.type === 'action-question') {
    const isProjectSlot = card.slotKind === 'project';
    const isMetadataSlot = card.slotKind === 'metadata';

    return (
      <div className="chopperActionCard questionCard" role="region" aria-label="Action Question">
        <div className="actionCardHeader">
          <span className="actionBadge">{card.actionTitle || 'Chopper Action'}</span>
          <h4>{card.label}</h4>
        </div>
        <p className="actionPrompt">{card.question}</p>
        {card.notice && <div className="actionNotice warning"><AlertTriangle size={14}/><span>{card.notice}</span></div>}

        {/* Direct upload buttons for file/folder slots */}
        {isProjectSlot && onUploadFolder && (
          <div className="actionUploadRow">
            <button
              type="button"
              className="actionUploadDirectBtn"
              disabled={disabled}
              onClick={onUploadFolder}
            >
              <FolderUp size={16}/> Choose / Upload Project Folder
            </button>
          </div>
        )}

        {isMetadataSlot && onUploadFile && (
          <div className="actionUploadRow">
            <button
              type="button"
              className="actionUploadDirectBtn"
              disabled={disabled}
              onClick={onUploadFile}
            >
              <FileUp size={16}/> Choose / Upload Metadata Workbook (.xlsx)
            </button>
          </div>
        )}

        {card.choices && card.choices.length > 0 && (
          <div className="actionChoices">
            {card.choices.map((choice, i) => (
              <button
                key={i}
                type="button"
                className="actionChoiceBtn"
                disabled={disabled}
                onClick={() => onAnswer(choice)}
              >
                {choice}
              </button>
            ))}
          </div>
        )}
        {card.optional && (
          <div className="actionCardFooter">
            <button
              type="button"
              className="actionSecondaryBtn"
              disabled={disabled}
              onClick={() => onAnswer('skip')}
            >
              Skip this step
            </button>
          </div>
        )}
      </div>
    );
  }

  if (card.type === 'action-plan') {
    const isMatchView = card.actionId === 'matchview';
    return (
      <div className="chopperActionCard planCard" role="region" aria-label="Action Plan Review">
        <div className="actionCardHeader">
          <span className="actionBadge plan">Review Action Plan</span>
          <h4>{card.actionTitle}</h4>
        </div>
        {card.description && <p className="actionDesc">{card.description}</p>}
        {card.notice && <div className="actionNotice info"><span>{card.notice}</span></div>}

        <div className="actionSlotSummary">
          {card.slotSummary?.map((slot, i) => (
            <div key={i} className="slotRow">
              <span className="slotLabel">{slot.label}:</span>
              <strong className="slotValue">{slot.value}</strong>
            </div>
          ))}
        </div>

        <div className="actionCardButtons">
          <button
            type="button"
            className="actionConfirmBtn"
            disabled={disabled}
            onClick={() => onAnswer('confirm')}
          >
            <Play size={14}/> Confirm & Execute
          </button>
          {isMatchView && (
            <button
              type="button"
              className="actionSwapBtn"
              disabled={disabled}
              onClick={() => onAnswer('swap')}
            >
              <RefreshCw size={13}/> Swap Base & Dev
            </button>
          )}
          <button
            type="button"
            className="actionCancelBtn"
            disabled={disabled}
            onClick={() => onAnswer('cancel')}
          >
            <Ban size={13}/> Cancel
          </button>
        </div>
      </div>
    );
  }

  if (card.type === 'action-summary') {
    const isBytecheck = card.actionId === 'bytecheck';
    const isMatchview = card.actionId === 'matchview';
    const isProjectPack = card.actionId === 'project_pack';
    const isFrd = card.actionId === 'create_frd';
    const isMom = card.actionId === 'create_mom';
    const isQualityReport = card.actionId === 'create_quality_report';

    return (
      <div className="chopperActionCard summaryCard" role="region" aria-label="Action Result Summary">
        <div className="actionCardHeader">
          <span className="actionBadge success"><CheckCircle2 size={13}/> Execution Complete</span>
          <h4>
            {isBytecheck && `ByteMap Validation — ${card.projectName || 'Project'}`}
            {isMatchview && `MatchView Comparison — Completed`}
            {isProjectPack && `Project Pack Created — ${card.projectName}`}
            {isFrd && `FRD Created — ${card.docTitle || 'Functional Requirements'}`}
            {isMom && `MOM Recorded — ${card.meetingSubject || 'Meeting Minutes'}`}
            {isQualityReport && `Quality / FAT Report — ${card.docTitle || 'Validation Report'}`}
          </h4>
        </div>

        {/* ByteCheck Counters */}
        {isBytecheck && card.counts && (
          <div className="summaryMetrics">
            <div className="metric pass">
              <span>Passed</span>
              <strong>{card.counts.pass}</strong>
            </div>
            <div className="metric fail">
              <span>Failed</span>
              <strong>{card.counts.fail}</strong>
            </div>
            <div className="metric warn">
              <span>Warning</span>
              <strong>{card.counts.warning}</strong>
            </div>
            <div className="metric info">
              <span>Groups</span>
              <strong>{card.counts.groups}</strong>
            </div>
          </div>
        )}

        {/* ByteCheck Top Fails */}
        {isBytecheck && card.topFails && card.topFails.length > 0 && (
          <div className="topIssuesList">
            <strong>Top Issues to Review:</strong>
            {card.topFails.map((fail, i) => (
              <div key={i} className="issueItem fail">
                <span className="issueParam">{fail.parameter}</span>
                <span className="issueMsg">{fail.message}</span>
                {fail.location && <code className="issueLoc">{fail.location}</code>}
              </div>
            ))}
          </div>
        )}

        {/* MatchView Counters */}
        {isMatchview && card.summary && (
          <div className="summaryMetrics">
            <div className="metric pass">
              <span>Added</span>
              <strong>{card.summary.added}</strong>
            </div>
            <div className="metric fail">
              <span>Removed</span>
              <strong>{card.summary.removed}</strong>
            </div>
            <div className="metric warn">
              <span>Modified</span>
              <strong>{card.summary.modified}</strong>
            </div>
            <div className="metric info">
              <span>Unchanged</span>
              <strong>{card.summary.unchanged}</strong>
            </div>
          </div>
        )}

        {/* MatchView Top Changed */}
        {isMatchview && card.topChanged && card.topChanged.length > 0 && (
          <div className="topIssuesList">
            <strong>Top Changed Files:</strong>
            {card.topChanged.map((ch, i) => (
              <div key={i} className="issueItem info">
                <code className="issueLoc">{ch.path}</code>
                <span className="issueCat">{ch.category}</span>
                <span className={`issueStatus ${ch.status}`}>{ch.status}</span>
              </div>
            ))}
          </div>
        )}

        {/* Project Pack Checklist */}
        {isProjectPack && card.documents && (
          <div className="docChecklist">
            <div className="metaSummary">
              <span>Customer: <b>{card.customer || 'Internal'}</b></span>
              <span>Department: <b>{card.department}</b></span>
            </div>
            <strong>Generated Document Drafts:</strong>
            {card.documents.map((doc, i) => (
              <div key={i} className="docItem">
                <FileText size={15}/>
                <span className="docTitle">{doc.title}</span>
                <span className="docStatus">{doc.status}</span>
              </div>
            ))}
          </div>
        )}

        {/* FRD Document Summary */}
        {isFrd && (
          <div className="docChecklist">
            <div className="metaSummary">
              <span>Document #: <b>{card.documentNumber || 'Draft ready'}</b></span>
              <span>Customer: <b>{card.customer || 'Internal'}</b></span>
              <span>Department: <b>{card.department || 'General'}</b></span>
            </div>
            {card.scope && <p style={{fontSize: 12, margin: '6px 0', color: 'var(--muted)'}}><b>Scope:</b> {card.scope}</p>}
            {card.acceptanceCriteria && <p style={{fontSize: 12, margin: '6px 0', color: 'var(--muted)'}}><b>Acceptance:</b> {card.acceptanceCriteria}</p>}
            {card.requirements && card.requirements.length > 0 && (
              <>
                <strong style={{display: 'block', margin: '8px 0 4px'}}>Requirements Defined ({card.requirements.length}):</strong>
                {card.requirements.map((req: any, i: number) => (
                  <div key={i} className="docItem">
                    <FileText size={15}/>
                    <span className="docTitle"><b>{req.id}</b>: {req.description || req.title}</span>
                    <span className="docStatus">{req.priority || 'high'}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        )}

        {/* MOM Document Summary */}
        {isMom && (
          <div className="docChecklist">
            <div className="metaSummary">
              <span>Document #: <b>{card.documentNumber || 'Draft ready'}</b></span>
              <span>Customer: <b>{card.customer || 'Internal'}</b></span>
              <span>Department: <b>{card.department || 'General'}</b></span>
            </div>
            {card.decisions && card.decisions.length > 0 && (
              <>
                <strong style={{display: 'block', margin: '8px 0 4px'}}>Key Decisions ({card.decisions.length}):</strong>
                {card.decisions.map((dec: any, i: number) => (
                  <div key={i} className="docItem">
                    <CheckCircle2 size={14} style={{color: '#059669', flexShrink: 0}}/>
                    <span className="docTitle">{dec.decision || dec.title || dec}</span>
                  </div>
                ))}
              </>
            )}
            {card.actions && card.actions.length > 0 && (
              <>
                <strong style={{display: 'block', margin: '8px 0 4px'}}>Action Items ({card.actions.length}):</strong>
                {card.actions.map((act: any, i: number) => (
                  <div key={i} className="docItem">
                    <Clock size={14} style={{color: '#d97706', flexShrink: 0}}/>
                    <span className="docTitle">{act.task || act} {act.owner && <small>({act.owner})</small>}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        )}

        {/* Quality / FAT Report Summary */}
        {isQualityReport && (
          <div className="docChecklist">
            <div className="metaSummary">
              <span>Report #: <b>{card.documentNumber || 'Draft ready'}</b></span>
              <span>Customer: <b>{card.customer || 'Internal'}</b></span>
              <span>Department: <b>{card.department || 'General'}</b></span>
            </div>
            {card.testScope && <p style={{fontSize: 12, margin: '6px 0', color: 'var(--muted)'}}><b>Scope:</b> {card.testScope}</p>}
            {card.acceptanceCriteria && <p style={{fontSize: 12, margin: '6px 0', color: 'var(--muted)'}}><b>Standards:</b> {card.acceptanceCriteria}</p>}
            {card.cases && card.cases.length > 0 && (
              <>
                <strong style={{display: 'block', margin: '8px 0 4px'}}>Validation Test Cases ({card.cases.length}):</strong>
                {card.cases.map((c: any, i: number) => (
                  <div key={i} className="docItem">
                    <CheckCircle2 size={14} style={{color: '#059669', flexShrink: 0}}/>
                    <span className="docTitle"><b>{c.id}</b>: {c.title || c.objective}</span>
                    <span className="docStatus">Passed</span>
                  </div>
                ))}
              </>
            )}
          </div>
        )}

        {/* Deep Link Button */}
        {card.deepLink && (
          <div className="actionCardFooter">
            <button
              type="button"
              className="actionPrimaryBtn"
              onClick={() => {
                if (isBytecheck) {
                  window.dispatchEvent(new CustomEvent('usopp-adopt-validation', {detail: card}));
                  navigateRoute({page: 'validation'});
                } else if (isMatchview) {
                  window.dispatchEvent(new CustomEvent('usopp-adopt-compare', {detail: card}));
                  navigateRoute({page: 'compare'});
                } else if (isProjectPack) {
                  if (card.projectId) {
                    window.dispatchEvent(new CustomEvent('workhub-open-project', {detail: {project: card.projectId}}));
                  }
                  navigateRoute({
                    page: 'home',
                    hubView: 'projects',
                    workhubProject: card.projectId || null,
                    workhubSection: 'overview',
                  });
                } else if (isFrd || isMom || isQualityReport) {
                  if (card.scopeId) {
                    navigateRoute({
                      page: 'home',
                      hubView: 'documents',
                      documentScope: card.scopeId,
                      documentStage: isMom ? 'meetings' : isQualityReport ? 'quality' : 'frd',
                    });
                  } else {
                    navigateRoute({
                      page: 'home',
                      hubView: 'documents',
                      documentKind: isMom ? 'mom' : isQualityReport ? 'quality' : 'frd',
                    });
                  }
                } else if (card.deepLink?.page) {
                  navigateRoute({page: card.deepLink.page});
                }
                if (onOpenFeature) {
                  onOpenFeature(card.deepLink?.page || 'home');
                }
              }}
            >
              <ExternalLink size={14}/> Open details in {card.deepLink.page === 'validation' ? 'ByteMap' : card.deepLink.page === 'compare' ? 'MatchView' : 'WorkHub'}
            </button>
          </div>
        )}
      </div>
    );
  }

  if (card.type === 'action-error') {
    return (
      <div className="chopperActionCard errorCard">
        <div className="actionCardHeader">
          <span className="actionBadge error"><XCircle size={13}/> Action Error</span>
        </div>
        <p className="errorMsg">{card.message}</p>
      </div>
    );
  }

  return null;
}
