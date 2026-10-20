export type Item = Record<string, any>;
export type Project = {
  id: string; name: string; status: string; progress?: Item;
  model?: Item; runtime?: Item; settings?: Item; watchlist?: string[];
  manualCorrections?: Item; scenario?: Item; [key: string]: any;
};
export const API = '/api/virtual-plc';
export async function request<T = Item>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(API + path, {
    credentials: 'same-origin', ...options,
    headers: { ...(options.body && !(options.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}), ...options.headers },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body.error || body); } catch { /* HTTP status remains useful. */ }
    if (response.status === 401) message = 'Sign in to uSOPp first, then reopen Virtual PLC.';
    throw new Error(message);
  }
  if (response.status === 204) return {} as T;
  return response.json();
}
export const post = <T = Item>(path: string, body: any = {}) => request<T>(path, {method: 'POST', body: JSON.stringify(body)});
export const list = (value: any): Item[] => Array.isArray(value) ? value : [];
export const text = (value: any, empty = '—'): string => value === undefined || value === null || value === '' ? empty : typeof value === 'object' ? JSON.stringify(value) : String(value);
export const valueText = (value: any): string => typeof value === 'boolean' ? (value ? 'TRUE' : 'FALSE') : text(value);
export function memoryValue(project: Project | null, name: string | undefined) {
  if (!name) return undefined;
  const memory = project?.runtime?.memory || {};
  if (Object.prototype.hasOwnProperty.call(memory, name)) return memory[name];
  const variables = list(project?.runtime?.variables);
  const exact = variables.find(v => v.id === name || `${v.scope}.${v.name}` === name);
  if (exact) return exact.value;
  const matches = variables.filter(v => project?.model?.symbolCaseSensitive ? v.name === name : v.name?.toLowerCase() === name.toLowerCase());
  return matches.length === 1 ? matches[0].value : undefined;
}
export function download(name: string, content: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function exportRows(name: string, rows: Item[]) {
  const fields = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const cell = (value: any) => { let result = text(value, ''); if (/^[=+@\-\t\r]/.test(result)) result = "'" + result; return '"' + result.replaceAll('"', '""') + '"'; };
  download(name, '\ufeff' + [fields.map(cell).join(','), ...rows.map(row => fields.map(field => cell(row[field])).join(','))].join('\r\n'), 'text/csv;charset=utf-8');
}
export function parseValue(input: string, type?: string) {
  if (type?.toUpperCase() === 'BOOL') {
    if (/^(true|1)$/i.test(input)) return true;
    if (/^(false|0)$/i.test(input)) return false;
    throw new Error('Enter TRUE, FALSE, 1 or 0 for BOOL.');
  }
  if (/^(S?INT|U?D?INT|L?REAL|BYTE|WORD|DWORD|LWORD|TIME|USINT|UDINT|DINT|ULINT|LINT)$/i.test(type || '')) {
    const value = Number(input); if (!Number.isFinite(value)) throw new Error('Enter a finite numeric value.'); return value;
  }
  try { return JSON.parse(input); } catch { return input; }
}
export function sourcePath(item: Item | undefined): string {
  return typeof item?.source === 'object' ? item.source?.path || '' : item?.source || item?.path || '';
}

export function hmiTextGroup(project: Project, object: Item): Item | undefined {
  const groups = project.model?.hmi?.textGroups || {};
  const raw = object.textGroup || object.properties?.TextGroup || object.properties?.textGroup;
  if (typeof raw !== 'string') return undefined;
  if (groups[raw]) return groups[raw];
  const name = (/TextGroup\[([^\]]+)\]/i.exec(raw)?.[1] || raw).replace(/\.txtgrp$/i, '').toLowerCase();
  const matches = Object.entries(groups).filter(([path]) => path.replaceAll('\\', '/').split('/').pop()?.replace(/\.txtgrp$/i, '').toLowerCase() === name);
  return matches.length === 1 ? matches[0][1] as Item : undefined;
}

export function virtualVariable(project: Project, name: string): Item | undefined {
  const rows = [...list(project.runtime?.variables), ...list(project.model?.variables)];
  const exact = rows.find(row => row.id === name);
  if (exact) return exact;
  const candidates = [...new Map(rows.filter(row => project.model?.symbolCaseSensitive ? row.name === name : row.name?.toLowerCase() === name?.toLowerCase()).map(row => [row.id, row])).values()];
  const globals = candidates.filter(row => ['global', '@global', ''].includes(String(row.scope || '').toLowerCase()));
  return globals.length === 1 ? globals[0] : candidates.length === 1 ? candidates[0] : undefined;
}
export function answerText(answer: any): string {
  if (typeof answer !== 'string') return text(answer, 'No answer was returned.');
  try {
    const parsed = JSON.parse(answer);
    const paragraphs = Array.isArray(parsed) ? parsed : parsed.paragraphs;
    if (Array.isArray(paragraphs)) return paragraphs.map(p => `${p.text || ''}${Array.isArray(p.sourceIds) && p.sourceIds.length ? ' ' + p.sourceIds.map((id: string) => `[${id}]`).join(' ') : ''}`).join('\n\n');
  } catch { /* Plain answers already contain their source references. */ }
  return answer;
}
