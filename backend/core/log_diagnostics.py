"""Explain rejected YBS captures directly from bytes before model generation."""
import re
from python_engine.ybs import frame_findings


def reply_if_invalid_ybs(context, question):
    summary=context.get('logSummary')
    if not isinstance(summary,dict) or not isinstance(summary.get('captures'),list): return None
    explicit=bool(re.search(r'\b(?:crc|checksum|frame|capture|packet|decode|decoding|log|YBS)\b|\b(?:GC|group\s*(?:code)?)\s*\d+',str(question),re.I))
    attachments=context.get('attachments') or []
    has_reports=isinstance(attachments,list) and any(isinstance(item,dict) and item.get('kind')=='report' for item in attachments)
    error_question=bool(re.search(r'\b(?:error|errors|failed|failure|failures|wrong)\b',str(question),re.I)) and not has_reports
    if not summary.get('selectedCapture') and not explicit and not error_question:return None
    findings=[]
    for capture in summary['captures'][:40]:
        if not isinstance(capture,dict): continue
        raw=capture.get('responseBytes')
        if not isinstance(raw,list) or not raw or len(raw)>65535 or any(type(v) is not int or not 0<=v<=255 for v in raw): continue
        if capture.get('protocol')!='ybs' and raw[0]!=241: continue
        group=capture.get('groupCode'); machine=capture.get('machineId')
        group=group if type(group) is int and 0<=group<=65535 else None
        machine=machine if type(machine) is int and 0<=machine<=255 else None
        metadata=capture.get('expectedLength');metadata=metadata if type(metadata) is int and 0<=metadata<=65535 else None
        result=frame_findings(raw,machine,group,metadata)
        if result['success']: continue
        location=f"response line {capture['responseLine']}" if type(capture.get('responseLine')) is int else str(capture.get('timestamp') or 'selected capture')[:100]
        result.update(location=location,asset=str(capture.get('asset') or '')[:200],groupCode=group if group is not None else result['groupCode'])
        findings.append(result)
    if not findings:return None
    lines=[f'{len(findings)} supplied YBS response(s) failed frame validation. Parameter readings are withheld for these frames.']
    for result in findings[:10]:
        lines.extend(['',f'GC {result["groupCode"]} - {result["location"]}', 'Confirmed byte errors (positions start at 0):'])
        for row in result['checks']:
            if not row['passed']:
                position=f'byte {row["offset"]}' if row['offset'] is not None else 'frame'
                lines.append(f'- {row["name"]}, {position}: expected {row["expected"]}; received {row["actual"]}.')
        lines.append(f'Header total length: {result["frameLength"]} bytes. Captured: {result["capturedBytes"]} bytes.')
        if result['metadataBytes'] is not None:
            lines.append(f'Header-declared data: {result["dataLength"]} bytes. Metadata: {result["metadataBytes"]} bytes. Matching lengths do not establish frame integrity.' if result['dataLength']==result['metadataBytes'] else f'Metadata also differs: expected {result["metadataBytes"]} data bytes; header declares {result["dataLength"]}.')
        if result['trailerNote']:lines.append('Possible cause: '+result['trailerNote'])
        lines.extend(['Next checks:',*[f'{index}. {action}' for index,action in enumerate(result['nextActions'],1)],
                      'The capture does not identify whether firmware, transport handling or logging introduced the error.'])
    if len(findings)>10:lines.append(f'{len(findings)-10} additional rejected frames are included in the structured findings. Select one capture for its byte details.')
    return dict(answer='\n'.join(lines),source='local-ybs-frame-diagnostics',model=None,evidence=[],frameFindings=findings)
