// MIN/MAX are engineering references, not acceptance criteria for DataInspect.
export function dataQualityIssue(value: unknown, parameter: string): string | undefined {
  if (value === null || value === undefined) return 'No complete decoded value. Check payload length, datatype and byte offset.';
  if (Array.isArray(value)) return value.map(v => dataQualityIssue(v, parameter)).find(Boolean);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'Non-finite numeric value. Check datatype, byte order and offset.';
    if (/e\+/i.test(String(value))) return 'Positive-exponent scientific value. Check datatype, byte order, offset and scale factor.';
  }
  if (typeof value === 'string' && /lot[\s_-]*name/i.test(parameter) && !value.trim()) return 'Lot name is empty. Check the PLC lot-name variable and STRING mapping.';
  return undefined;
}
