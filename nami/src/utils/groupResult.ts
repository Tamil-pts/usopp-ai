import {GroupResponseData} from '../types';

export function groupOutcome(result: GroupResponseData): 'passed' | 'failed' | 'mismatch' | 'skipped' {
  if (result.stage === 'not_sent') return 'skipped';
  if (!result.success) return 'failed';
  if (!result.lengthMatch) return 'mismatch';
  if (result.parsedValues.some((value) => value.rawValue === null || !value.isInRange)) return 'failed';
  return 'passed';
}

export function closeDescription(close: GroupResponseData['closeResult']): string {
  if(close?.warning&&!close.sentBytes?.length)return close.warning;
  if (close?.sentBytes?.length) return 'GC 11 close request sent; no reply frame is expected.';
  return close?.error || 'GC 11 could not be sent because no usable TCP connection remained.';
}
