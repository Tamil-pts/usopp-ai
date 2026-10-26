// The global Chopper launcher and the lazy WorkHub builder share a bounded draft request.
let pending:string|null=null;
export function isWorkHubDashboardRequest(text:string){
 if(/\b(report|spreadsheet|workbook|log decoder)\b/i.test(text)&&!/\bworkhub\b/i.test(text))return false;
 return /\b(create|build|add|show|open|change|convert|switch|make|resize|larger|smaller)\b/i.test(text)&&(
  /\b(dashboard|widget)\b/i.test(text)||/\b(chart|graph|heatmap|card)\b/i.test(text)&&/\b(project|tasks?|engineer|validation|activity|approval|milestone|knowledge)\b/i.test(text));
}
export function openDashboardBuilder(prompt=''){
 pending=/^\s*(?:please\s+)?open\s+(?:my\s+|the\s+)?dashboard[.!]?\s*$/i.test(prompt)?'':prompt.slice(0,4000);window.dispatchEvent(new CustomEvent('workhub-open-dashboard'));
}
export function takeDashboardRequest(){const value=pending;pending=null;return value;}
