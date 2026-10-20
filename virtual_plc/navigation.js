/* Additive navigation for the unchanged uSOPp React shell, in dev and release. */
(() => {
  if (window.__usoppVirtualNavigation) return;
  window.__usoppVirtualNavigation = true;
  const icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/><path d="M9 9h6v6H9z"/></svg>';
  const arrow = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10"/></svg>';
  const style = document.createElement('style');
  style.id = 'virtual-plc-navigation-style';
  style.textContent = `
    .workspaceApp .railMainNav .virtualPlcNav {
      border:1px solid transparent;background:transparent;color:#c6dfe7;
      border-radius:8px;min-height:62px;padding:10px 4px;display:flex;
      flex-direction:column;align-items:center;justify-content:center;gap:6px;
      font:inherit;font-size:.8125rem;text-decoration:none;text-align:center;
    }
    .workspaceApp .railMainNav .virtualPlcNav:hover{background:#124d60;color:#fff}
    .workspaceApp .railMainNav .virtualPlcNav:focus-visible{outline:2px solid #82e9cc;outline-offset:2px}
    .workspaceApp .railMainNav .virtualPlcNav svg{width:20px;height:20px;flex:none}
    .workHubTaskGrid .virtualPlcCard{color:var(--text);text-decoration:none;text-align:left;font:inherit}
    .workHubTaskGrid .virtualPlcCard svg{width:22px;height:22px;flex:none}
    .workHubTaskGrid .virtualPlcCard:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
    @media(max-width:1100px){.workspaceApp .railMainNav .virtualPlcNav{min-height:54px;padding:6px 2px}}
    @media(max-width:680px){.workspaceApp .railMainNav .virtualPlcNav{flex-direction:row;min-height:38px;gap:7px}}
  `;
  document.head.appendChild(style);

  function attach() {
    const nav = document.querySelector('.workspaceApp .railMainNav[aria-label="Main navigation"]');
    if (nav && !nav.querySelector('#virtual-plc-navigation')) {
      const link = document.createElement('a');
      link.id = 'virtual-plc-navigation';
      link.className = 'virtualPlcNav';
      link.href = '/virtual-plc/';
      link.setAttribute('aria-label', 'Open Virtual PLC workspace');
      link.title = 'Virtual PLC: controller, logic, I/O and HMI simulation';
      link.innerHTML = icon + '<span>Virtual PLC</span>';
      nav.appendChild(link);
    }
    const grid = document.querySelector('.workHubTaskGrid');
    if (grid && !grid.querySelector('#virtual-plc-workhub')) {
      const card = document.createElement('a');
      card.id = 'virtual-plc-workhub';
      card.className = 'workHubTask virtualPlcCard';
      card.href = '/virtual-plc/';
      card.innerHTML = '<div class="workHubTaskTop"><span class="workHubToolIcon">' + icon +
        '</span><span class="workHubToolName">Virtual PLC</span>' + arrow + '</div>' +
        '<h3>Explore and simulate your PLC project</h3>' +
        '<p>Inspect the controller, tasks and logic. Run supported code with shared virtual I/O and HMI memory.</p>' +
        '<span class="workHubTaskDetail">Project &rarr; virtual workspace' + arrow + '</span>';
      grid.appendChild(card);
    }
  }
  let scheduled = false;
  new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; attach(); });
  }).observe(document.documentElement, {childList: true, subtree: true});
  attach();
})();
