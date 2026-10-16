"""Window-specific workflow help; engineering verdicts remain in their results."""
GUIDES={
 'home':('WorkHub','Choose your next engineering task and review saved activity.',[
  'Open ByteMap to select a project and inspect packet layouts.',
  'Use DataInspect for PLC reads or a personal dashboard; MatchView compares revisions.',
  'Run configured requirements in LogicScan. Open saved activity to review evidence.']),
 'validation':('ByteMap / MetaWorks','Validate packet structures and generate metadata from the selected project.',[
  'Select the machine/department, project and active configuration. Add reference metadata when needed.',
  'Run validation, then inspect each issue by Group Code, tag, source file and line.',
  'For metadata, review readable parameter names, datatypes, offsets and Sheet2 dropdown mappings before exporting.',
  'Correct the source or reviewed mapping, then rerun validation.']),
 'plc':('DataInspect','Read packets, inspect manual captures and build live or report dashboards.',[
  'Manage targets: choose Real PLC, Automation Studio simulation or the metadata-driven Data simulator.',
  'Load the correct metadata and check GC 10 before reading other groups.',
  'Select a Group Code and read data, or paste Manual PLC received data. Review capture time and source.',
  'Open My dashboards to choose a layout, add widgets or formulas and adjust sizes. View source reveals each binding.',
  'Enable live collection explicitly per target. Storage is optional and limited to 30 days; collection continues on the server.']),
 'compare':('MatchView','Compare two project revisions with separate target and source evidence.',[
  'Select the baseline and developed projects in the correct order.',
  'Confirm the active configurations and HMI targets, then run comparison.',
  'Inspect individual changed properties, logic and declarations. Export the selected report sections.']),
 'rules':('LogicScan','Run reviewed requirements against the selected project.',[
  'Select the project and machine/department, then choose a feature pipeline.',
  'Review rule requirements, accepted alternatives and every cross reference in KnowHub.',
  'Run validation and expand the failed check to compare expected and actual evidence.',
  'Use one matching Lapformer reference variant. Reference drafts describe supplied source; review before enabling.']),
 'chatbot':('Chopper / KnowHub','Ask engineering questions and configure reviewed knowledge.',[
  'Use Chat for explanations, machine sequences, log decoding and source references.',
  'Use Rule configuration to define complete logic, alternatives and cross references.',
  'Use KnowHub to review rules, data models, unit rules, dropdown mappings and dashboard layouts.']),
 'settings':('Settings','Configure your workspace and the shared Chopper connection.',[
  'Local CPU model is the default. Activate an installed GGUF, or use the one-time CPU model setup.',
  'A Ready indicator means the model is responding; Starting means loading is still in progress.',
  'Keep Start with server enabled for automatic loading. Advanced settings hold model paths, CPU limits and external connections.',
  'Choose local engineering tools if you want validation and log decoding without a model.']),
 'help':('Help','Find feature guides and the next action for your workflow.',[
  'Choose the relevant workspace guide.',
  'Ask Chopper about the current window, or open full Chat for logs and project analysis.'])
}

def guide(context):
    window=context.get('currentWindow')
    if not isinstance(window,dict) or window.get('page') not in GUIDES:return None
    name,purpose,steps=GUIDES[window['page']]
    return {'name':name,'purpose':purpose,'steps':steps}

def answer(context):
    item=guide(context)
    if not item:return None
    window=context['currentWindow'];lines=[item['name'],item['purpose'],'']
    details=window.get('details')
    if isinstance(details,dict):
        # Captured values are displayed as evidence, never used to invent a verdict.
        for key in ('view','dialog','target','machine','groupCode','captureTime','captureSource','captureStatus','dataCheckStatus','findingSummary'):
            if details.get(key) is not None:lines.append(f'{key}: {str(details[key])[:160]}')
    counts=context.get('counts')
    if isinstance(counts,dict) and counts:lines.append('Reported result counts: '+', '.join(f'{key}: {value}' for key,value in counts.items() if key in {'pass','warn','fail'}))
    lines.extend(['',*[f'{index+1}. {step}' for index,step in enumerate(item['steps'])]])
    findings=window.get('findings')
    if isinstance(findings,list) and findings:
        lines.extend(['','Current findings (reported evidence):'])
        for finding in findings[:5]:
            if isinstance(finding,dict):lines.append(str(finding.get('actual') or finding.get('message') or finding.get('description') or finding.get('name') or finding.get('id') or '')[:500])
        lines.append('Open the finding to review expected/actual values and source evidence before making a correction.')
    return '\n'.join(lines)
