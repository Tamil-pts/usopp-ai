/** Display precision only: retain original PLC values for range checks and diagnostics. */
export function formatDecodedValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? '1 : ON' : '0 : OFF';
  if (typeof value === 'number') return Number.isFinite(value) ? String(Number(value.toFixed(4))) : String(value);
  if (Array.isArray(value)) return `[${value.map(entry => entry == null ? 'Buffer Overflow' : formatDecodedValue(entry)).join(', ')}]`;
  return String(value ?? '');
}
