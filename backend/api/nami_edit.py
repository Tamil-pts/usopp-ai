"""Prepare and explicitly send a source-mapped settings edit."""
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException
from backend.api import nami
from backend.core import nami_transport as tcp
from backend.core import nami_edit as edit
from backend.core.run_history import current_user

router=APIRouter(prefix='/api/nami/plc',tags=['DataInspect settings'])
_pending={}
_lock=threading.Lock()


def owner(): return (current_user.get() or {}).get('id','local')


@router.post('/prepare-edit')
def prepare(data:dict):
    try:
        if nami.is_ybs(data): raise ValueError('YBS settings writes require a verified YBS write protocol. B&R write frames cannot be sent to YBS.')
        if data.get('isSimulated'): raise ValueError('The built-in measurement simulator has no settings write service. Select the Automation Studio or PLC write service.')
        ip,_,mid,timeout=nami.target(data)
        port=nami.number(data,'writePort',21011,1,65535)
        row=data.get('parameter')
        if not isinstance(row,dict): raise ValueError('Select a metadata parameter.')
        rows=data.get('metadata')
        if not isinstance(rows,list) or len(rows)>30000 or row not in rows: raise ValueError('The selected parameter must be part of the loaded metadata.')
        if any(not isinstance(r,dict) or r.get('protocol')=='ybs' for r in rows):raise ValueError('Load matching SpinConnect metadata before editing.')
        variant,field=edit.select_field(data.get('mapping'),row,str(data.get('variantId','')))
        order=(data.get('plc') or {}).get('endianness',data.get('endianness','little'))
        if order not in ('little','big'): raise ValueError('Select the PLC payload byte order.')
        with tcp.connection(ip,port,timeout) as sock:
            try:
                read=tcp.exchange(sock,tcp.read_request(mid,row['groupCode']))
                baseline=edit.checked_payload(read,variant['readPayloadBytes'])
            finally: tcp.request_close(sock,mid,'edit-prepare')
        value=edit.unpack(baseline,field,order)
        token=secrets.token_urlsafe(32)
        with _lock:
            now=time.monotonic()
            for key in list(_pending):
                if _pending[key]['expires']<now: del _pending[key]
            if len(_pending)>=500: raise HTTPException(429,'Too many pending edits. Wait for an earlier preview to expire.')
            _pending[token]=dict(owner=owner(),expires=now+120,data=data,variant=variant,field=field,baseline=baseline,
                                 target=(ip,port,mid,timeout),order=order)
        return dict(token=token,currentValue=value,expiresIn=120,field=field,
                    target=dict(ip=ip,port=port,machineId=mid),condition=variant['when'],
                    message='Current settings read from the write service. Enter a PLC value, then send the edit.')
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    except OSError as exc: raise HTTPException(502,str(exc)) from exc


@router.post('/send-edit')
def send(data:dict):
    with _lock:
        pending=_pending.get(str(data.get('token','')))
        if not pending or pending['owner']!=owner(): raise HTTPException(404,'Edit preview not found. Read current settings again.')
        if pending['expires']<time.monotonic():
            del _pending[data['token']]
            raise HTTPException(409,'Edit preview expired. Read current settings again.')
        try: replacement,value=edit.encode(data.get('value'),pending['field'],pending['order'],pending['data']['parameter'])
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc
        # Consume before any connection: a double click or retry cannot resend.
        del _pending[data['token']]
    ip,port,mid,timeout=pending['target'];original=pending['data'];row=original['parameter'];variant=pending['variant'];field=pending['field']
    identity=nami.start_inspect(dict(original,port=port,groupCode=row['groupCode']),'write-parameter')
    sent=False
    result=dict(success=False,groupCode=row['groupCode'],rawBytes=[],sentBytes=[],verified=False)
    try:
        with tcp.connection(ip,port,timeout) as sock:
            try:
                before=tcp.exchange(sock,tcp.read_request(mid,row['groupCode']))
                baseline=edit.checked_payload(before,variant['readPayloadBytes'])
                if baseline!=pending['baseline']: raise ValueError('Settings changed after preview. Read current settings again before sending.')
                request=edit.build_write(mid,row['groupCode'],baseline,variant,field,replacement)
                sent=True  # Once sending starts, a transport failure has an uncertain outcome.
                result=tcp.exchange(sock,request)
                result.update(groupCode=row['groupCode'],verified=False,resultCode=result['rawBytes'][2] if len(result['rawBytes'])>=7 else None)
                if not result.get('success'): raise ValueError(result.get('error') or 'Write response was not received.')
                accepted=result['resultCode']==0
                after=tcp.exchange(sock,tcp.read_request(mid,row['groupCode']))
                result['readback']=after
                observed=edit.checked_payload(after,variant['readPayloadBytes'])
                verified=observed[field['readOffset']:field['readOffset']+field['size']]==replacement
                result.update(success=accepted and verified,verified=accepted and verified,
                              requestedValue=value,observedValue=edit.unpack(observed,field,pending['order']))
                if not accepted: result['error']=edit.RESULTS.get(result['resultCode'],f'PLC result code {result["resultCode"]}.')
                elif not verified: result['error']='PLC acknowledged the group, but the selected value was not confirmed by readback.'
                else: result['message']='PLC acknowledged the write and the selected value was confirmed by readback.'
            finally: result['closeResult']=tcp.request_close(sock,mid,'edit-send')
    except (ValueError,OSError) as exc:
        result.update(success=False,error=str(exc)+( ' The write may have been applied. Read current settings before another attempt.' if sent else ' No settings write was confirmed sent.'))
    result.update(writeAttempted=sent,parameter=dict(tagCode=row.get('tagCode'),offset=row['offset'],parameter=row.get('parameter')),
                  writeEvidence=dict(project=original['mapping'].get('project'),sourceFingerprint=original['mapping'].get('sourceFingerprint'),
                                     variant=variant['when'],fieldId=field['id'],beforeValue=edit.unpack(pending['baseline'],field,pending['order']),
                                     requestedValue=value,target=dict(ip=ip,port=port,machineId=mid)))
    return nami.finish_inspect(identity,result)
