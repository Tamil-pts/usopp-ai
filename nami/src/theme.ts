import {userStorage} from '../../src/shared/userStorage';
// The PLC workspace follows the hosting application's theme, including changes
// made while it is open. Direct access uses the same saved preference.
function syncTheme() {
  let theme = userStorage.getItem('usopp_theme') === 'dark' ? 'dark' : 'light';
  try {
    if (window.parent !== window) theme = window.parent.document.documentElement.dataset.theme || theme;
  } catch { /* A separately hosted preview has its own saved preference. */ }
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}
syncTheme();
window.addEventListener('storage', syncTheme);
try {
  if (window.parent !== window) {
    new MutationObserver(syncTheme).observe(window.parent.document.documentElement, {attributes:true, attributeFilter:['data-theme']});
  }
} catch { /* Cross-origin previews cannot observe their parent. */ }
