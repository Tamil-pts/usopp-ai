"""Additional fictional training records; never production work or approval data."""
from copy import deepcopy
from .authoring import blank

def extend(value):
    value['sample_version']='2'
    value['project'].update(title='Ring Frame PLC Upgrade',number='DEMO-PRJ-001',customer='Demo Textile Mills',machine='Ring Frame',department='Engineering Services',team='PLC')
    value['meeting']={'title':'Ring Frame motor trip alarm modification','date':'2026-01-15','participants':'Engineer A; Engineer B','agenda':'Review trip indication, alarm retention and permitted reset conditions.','discussion_notes':'Confirm the reset permissive and retention requirement before approval.','decisions':'Trip feedback is detected and the HMI shows the alarm. Reset conditions remain subject to engineering review.','action_items':'Engineer A: draft FRD. Engineer B: clarify the reset condition. Due dates not confirmed.','open_questions':'Is reset permitted while the motor is running? Is retention across power cycling required?'}
    value['assignment']={'responsible':'Engineer A','supporting':['Engineer B'],'assigned_at':'2026-01-15','responsibility':'PLC/HMI alarm modification','remarks':'Fictional reference assignment','status':'Assigned','notifications':['Engineer A: project assigned.','Engineer B: supporting engineer assignment.'],'history':[{'event':'Created','detail':'Fictional project registered.'},{'event':'Assigned','detail':'Engineer A responsible; Engineer B supporting.'}]}
    value['documents']={s:blank(s) for s in ('corrections','test','fat','quality','closure')}
    corrections=value['documents']['corrections']
    corrections['summary']='Motor Trip Alarm Reset Logic Modification'
    corrections['changes']=[{'id':'CN-001','summary':'Review and correct the motor trip alarm reset logic after confirming the permitted operating conditions.','requirement_ids':['FR-003'],'source_ids':[],
      'existing_behavior':'Requires observation on the authorized PLC/HMI test setup.','expected_behavior':'Retain the alarm until the approved reset conditions are satisfied.','plc_references':'TRAIN_RESET_REQUEST / TRAIN_TRIP_ALARM — fictional references, actual program locations unconfirmed.','impact':'Review alarm retention, HMI indication and reset interlocks.','before_evidence':'','after_evidence':'','verification':''}]
    values={
      'corrections':{'Existing behavior':'Reset behavior requires engineering verification.','Observed problem':'Not confirmed by a physical observation.','Expected behavior':'Reset follows the approved operating conditions.','Required correction':'Review PLC reset logic and HMI reset command handling.','Assigned engineer':'Engineer A (fictional)','Impact analysis':'Assess alarm retention, interlocks and operator indication.'},
      'test':{'Validation objective':'Verify PLC/HMI motor trip alarm behavior against reviewed requirements.','Test environment':'Authorized B&R Automation Studio simulation or PLC test setup; details to be confirmed.','Validation scope':'Trip detection, alarm retention, reset and HMI indication.','Reference documents':'DEMO FRD revision R00 and CN-001; approval remains pending.'},
      'fat':{'Test scope':'Factory acceptance of motor trip indication and approved reset behavior.','Prerequisites':'Approved FRD, reviewed test procedure, authorized test environment and confirmed reset permissive.','Test environment':'Ring Frame PLC/HMI test setup, details unconfirmed.','Deviations':'Record observed deviations during execution. No execution performed in this reference.'},
      'quality':{'FRD revision verification':'Verify the exact approved FRD revision and resolved reset clarification.','Correction note disposition':'Review CN-001 and its before/after evidence.','Test report review':'Check TC-001 through TC-004 and supporting evidence.','FAT evidence verification':'Verify actual execution records and authorized sign-off.','Outstanding issues':'Reset permissive, test evidence and engineering approvals remain pending.'},
      'closure':{'Completion summary':'Completion is pending verification, approval and handover.','Final deliverables':'FRD, functional flowchart, CN-001, validation test report, FAT and final PLC/HMI deliverables.','Document revisions':'Record the approved revision of each deliverable.','Handover information':'Customer handover details not confirmed.','Open issues':'Reset conditions, verification evidence and quality approval remain pending.','Closure remarks':'Not ready for closure until the required verification and approvals are complete.'},
    }
    for kind,content in value['documents'].items():
        content['sections']=[{'heading':s['heading'],'text':values[kind].get(s['heading'],'')} for s in content['sections']]
        content['practice_status']='draft';content['practice_revision']=0;content['practice_history']=[]
    test=value['documents']['test']
    test['summary']='Motor trip PLC/HMI validation'
    test['cases']=[{'id':'TC-'+str(i+1).zfill(3),'objective':title,'procedure':procedure,'expected_result':expected,'acceptance_criteria':expected,'requirement_ids':refs,'source_ids':[],'execution':None} for i,(title,procedure,expected,refs) in enumerate([
      ('Activate motor trip feedback','Apply the trip input under approved test conditions.','The trip alarm activates.',['FR-001']),
      ('Maintain trip feedback','Keep trip feedback active and request reset.','The alarm remains latched.',['FR-003']),
      ('Clear trip feedback and request reset','Clear trip feedback, confirm approved permissives, then request reset.','Reset follows the confirmed operating conditions.',['FR-003']),
      ('Verify HMI alarm indication','Activate and clear the alarm under approved conditions.','The HMI shows the correct alarm state.',['FR-002'])])]
    value['documents']['fat'].update(summary='Motor trip alarm factory acceptance',cases=deepcopy(value['fat']['cases']))
    value['documents']['closure']['deliverables']=[{'id':'DEL-'+str(i+1).zfill(3),'title':t,'description':'Required project deliverable','expected_result':'Approved revision available','actual':'','evidence_ids':[],'status':'pending'} for i,t in enumerate(['Approved FRD','Validation and FAT evidence','Final PLC/HMI handover'])]
    value['supporting_document']={'title':'PLC/HMI motor trip change document','purpose':'Describe the reviewed technical change.','program_references':'Actual PLC program / HMI page references not yet confirmed.','technical_description':'Detect the trip, indicate the alarm, retain it and evaluate the approved reset condition.','findings':'Reset permissive remains an open clarification.','revision':'R00','review':'Draft — not approved'}
    value['library']=[{'id':'DEMO-LIB-'+k.upper(),'kind':k,'title':t,'revision':'R00','status':'Fictional approved reference','source_revision':'DEMO-'+k.upper()+'-R00'} for k,t in [('frd','Ring Frame motor trip requirements'),('mom','Motor trip meeting record'),('corrections','Alarm reset correction note'),('test','PLC/HMI validation procedure'),('fat','Motor trip factory acceptance'),('quality','Engineering quality checklist'),('closure','Project handover template')]]
    return value
