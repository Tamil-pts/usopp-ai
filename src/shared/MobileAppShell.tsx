import {useEffect, useState} from 'react';
import {Bot, FileText, FolderOpen, Inbox, LayoutDashboard, Smartphone, X} from 'lucide-react';
import type {WorkspacePage} from './WorkspaceNavigation';
import './mobile-app-shell.css';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{outcome: 'accepted' | 'dismissed'}>;
}

function isStandaloneMode(): boolean {
  return window.matchMedia?.('(display-mode: standalone)').matches || (window.navigator as {standalone?: boolean}).standalone === true;
}

function isIosSafari(): boolean {
  const ua = window.navigator.userAgent || '';
  return /iphone|ipad|ipod/i.test(ua) && /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
}

export function MobileInstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [iosTip, setIosTip] = useState(false);
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem('usopp_pwa_banner_dismissed') === '1');

  useEffect(() => {
    if (isStandaloneMode() || dismissed) return;
    if (isIosSafari()) setIosTip(true);
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredPrompt(event as BeforeInstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', onPrompt);
    return () => window.removeEventListener('beforeinstallprompt', onPrompt);
  }, [dismissed]);

  if (dismissed || isStandaloneMode() || (!deferredPrompt && !iosTip)) {
    return null;
  }

  const dismiss = () => {
    sessionStorage.setItem('usopp_pwa_banner_dismissed', '1');
    setDismissed(true);
  };

  const install = async () => {
    if (!deferredPrompt) return;
    await deferredPrompt.prompt();
    const result = await deferredPrompt.userChoice;
    if (result.outcome === 'accepted') {
      setDeferredPrompt(null);
      setDismissed(true);
    }
  };

  return (
    <div className="mobileInstallBanner" role="region" aria-label="Install uSOPp Mobile App">
      <div className="mobileInstallCopy">
        <Smartphone size={20} aria-hidden="true" />
        <div>
          <strong>Install uSOPp.ai Mobile App</strong>
          <span>
            {deferredPrompt
              ? 'Add to your home screen for full-screen WorkHub & Chopper access.'
              : 'Tap Share → "Add to Home Screen" in Safari to install.'}
          </span>
        </div>
      </div>
      <div className="mobileInstallActions">
        {deferredPrompt && (
          <button type="button" className="mobileInstallBtn" onClick={() => void install()}>
            Install
          </button>
        )}
        <button type="button" className="mobileInstallDismiss" aria-label="Dismiss install banner" onClick={dismiss}>
          <X size={15} />
        </button>
      </div>
    </div>
  );
}

export function MobileBottomNav({
  page,
  onSelectPage,
}: {
  page: WorkspacePage;
  onSelectPage: (target: WorkspacePage) => void;
}) {
  const [hubView, setHubView] = useState('dashboard');

  useEffect(() => {
    const onView = (event: Event) => {
      setHubView(String((event as CustomEvent).detail || 'dashboard').split(':')[0]);
    };
    window.addEventListener('workhub-view-changed', onView);
    return () => window.removeEventListener('workhub-view-changed', onView);
  }, []);

  const openHub = (view: string) => {
    onSelectPage('home');
    window.dispatchEvent(new CustomEvent('workhub-select-view', {detail: view}));
  };

  const openInbox = () => {
    onSelectPage('home');
    window.dispatchEvent(new CustomEvent('usopp-open-inbox', {detail: {view: 'mine'}}));
  };

  const openChopper = () => {
    window.dispatchEvent(new CustomEvent('usopp-open-chopper'));
  };

  return (
    <nav className="mobileBottomNav" aria-label="Mobile quick navigation">
      <button
        type="button"
        className={page === 'home' && (hubView === 'dashboard' || hubView === 'recent') ? 'active' : ''}
        onClick={() => openHub('dashboard')}
      >
        <LayoutDashboard aria-hidden="true" />
        <span>Overview</span>
      </button>
      <button
        type="button"
        className={page === 'home' && hubView === 'inbox' ? 'active' : ''}
        onClick={openInbox}
      >
        <Inbox aria-hidden="true" />
        <span>Inbox</span>
      </button>
      <button
        type="button"
        className={page === 'home' && hubView === 'projects' ? 'active' : ''}
        onClick={() => openHub('projects')}
      >
        <FolderOpen aria-hidden="true" />
        <span>Projects</span>
      </button>
      <button
        type="button"
        className={page === 'home' && hubView === 'documents' ? 'active' : ''}
        onClick={() => openHub('documents')}
      >
        <FileText aria-hidden="true" />
        <span>Docs</span>
      </button>
      <button
        type="button"
        className={page === 'chatbot' ? 'active' : ''}
        onClick={openChopper}
      >
        <Bot aria-hidden="true" />
        <span>Chopper</span>
      </button>
    </nav>
  );
}
