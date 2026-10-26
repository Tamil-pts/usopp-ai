import {lazy,Suspense,useState} from 'react';
import {useAccount} from '../account/AuthProvider';
import type {EngineeringFeature} from '../../shared/features';
const FRDSample=lazy(()=>import('./FRDSample').then(m=>({default:m.FRDSample})));

export type HelpDestination=EngineeringFeature|'home'|'settings'|'virtual-plc';
type Guide={id:string;title:string;purpose:string;prepare:string;steps:string[];result:string;check:string;page:HelpDestination;admin?:boolean};
const guides:Guide[]=[
 {id:'workhub-projects',title:'WorkHub - Automatic projects and iterations',purpose:'Record engineering work in shared projects with minimal data entry.',prepare:'Sign in with a personal account. Upload or select the project or metadata normally in the engineering tool.',steps:[
  'Run ByteMap, DataInspect, MatchView or LogicScan. WorkHub creates or finds the source project automatically and puts new work in Development.',
  'Open the project > Updates & evidence. Every new saved run is numbered Iteration 1, Iteration 2 and so on, with the tool, tester, test ID, recorded status and result evidence.',
  'Open an iteration to download its recorded result, available reports or uploaded project snapshot. Decoding the same DataInspect test or exporting another report stays in that iteration.',
  'Use Team activity for To do, In progress and Done cards. Filter by user, project or task and open a card to review its evidence.',
  'Active projects open on Workflow & timeline. Drag bars to move dates and drag either end to resize, or use the pencil to enter dates. Add your own steps, assignees, milestones and preceding steps. My work shows your assigned work on the same Gantt timeline.',
  'For work without an engineering run, create a project manually or add a short note and attachments under Updates & evidence. Completed projects show Summary, Updates & evidence, Issues and Approval history.'
 ],result:'A shared project and numbered development evidence, without re-entering each test as a daily update.',check:'Automatic capture applies to new personal-account runs. Older private history and demo results are not automatically published. Repeating a run does not approve its project.',page:'home'},
 {id:'workhub-planning',title:'WorkHub - Project templates and sprints',purpose:'Plan development, quality and release when creating a project.',prepare:'Choose the project owner and reviewers. Work type accepts an existing choice or your own text.',steps:[
  'Choose New project, name the work and select or type its Work type. Work type remains editable after development is finished.',
  'Choose Waterfall for sequential development, quality and release; Agile for repeated delivery sprints; Sprint for one focused sprint; or Custom for your own plan.',
  'Set the start date and, for Agile or Sprint, the sprint length and initial count. Drag the phase and sprint bars to set their periods before creating. Only the selected row changes.',
  'In Backlog & sprints, assign development tasks to a sprint or the backlog. Add sprint goals and owners, then start a sprint before starting its work.',
  'Complete sprint work, or move unfinished work to the backlog, before closing a sprint. Closing a sprint does not release the project.',
  'Overall completion includes development, quality and release. Development completed stays active; only Released / Closed reaches 100% and uses the completed project view.'
 ],result:'A project timeline with separate phase periods and editable work steps. Agile and Sprint also include a backlog and sprint board.',check:'Dragging dates changes planning only. Quality and release still require the assigned users to record their decisions.',page:'home'},
 {id:'workhub-approval',title:'WorkHub - Development, quality and release',purpose:'Finish development and optionally continue to quality check and release.',prepare:'Wait for active engineering runs to finish. Review their findings and deliverable evidence.',steps:[
  'The development assignee chooses Mark development completed. Work can remain at Development completed until review is required.',
  'Choose Send for quality check when needed. Select the quality reviewer and release approver by name and review the submitted deliverable or engineering iteration.',
  'The quality reviewer opens Approvals, reviews the evidence and chooses Quality passed or Request changes with a reason.',
  'The release approver chooses Approve release or Request changes. The release owner then chooses Mark released / Close.',
  'Requested changes return work to Development. Resolve the issue, record the next iteration and submit again. New development work returns completed projects to Development; checks by the assigned current reviewer stay at their review stage. Older decisions remain in history.',
  'Team activity keeps projects In progress until release is closed. Completed tasks can appear under Done while project review continues. Moving a card opens its permitted workflow confirmation; review actions belong to the named reviewer.'
 ],result:'Create and assign, Development, Development completed, Quality check, Release approval, Ready for release, Released / Closed.',check:'Engine results are evidence, not automatic approval. Existing decisions, tester names, iterations and submitted evidence stay recorded in project history.',page:'home'},
 {id:'workhub-notifications',title:'WorkHub - Notifications and Teams group sharing',purpose:'Receive in-app updates and share a prepared message in your existing Teams group.',prepare:'Use an existing Teams group that your colleagues can access. No Microsoft app registration is needed for manual chat sharing.',steps:[
  'Open Settings > Notifications and Teams sharing. Admin can save a Shared group chat link for everyone; optionally save your own group link.',
  'In the Teams group, open a message menu and choose Copy link. Paste that chat or message link into Settings and choose Group chat link as the method. Save notification settings.',
  'On a project, task or notification, choose Share in Teams. Review or edit the prepared message.',
  'Choose Copy & open Teams, then paste the message into the group and select Send. You can also copy the message separately.',
  'Use the review link to open WorkHub and record the quality or release decision. Chat sharing does not change task status.',
  'For colleagues on other computers, Admin can save the office WorkHub address in Settings. A localhost link points to the computer where the link is opened.',
  'Automatic email, Teams workflow and Microsoft application setup are optional collapsed settings for later, when company authorization is available.'
 ],result:'In-app notifications and user-controlled sharing to an existing Teams group.',check:'A chat link opens Teams; it does not send automatically. The sender pastes and sends the message. Approval history stays in WorkHub.',page:'settings'},
 {id:'start',title:'Start in WorkHub',purpose:'Choose a tool and return to your saved work.',prepare:'Sign in with an enabled account. New account requests need Admin approval.',steps:[
  'Open WorkHub for Portfolio, My work, Team activity, Recent work, Approvals and Reports. Choose engineering tools from the sidebar.',
  'Use ByteMap for SpinConnect source packets, DataInspect for SpinConnect readings, MatchView for revision changes, LogicScan for requirements, Chopper for questions, or Virtual PLC for simulation.',
  'Open WorkHub > Recent work to find a saved result. Filter by activity, status, project or test ID; Admin can also filter by user.',
  'Open a result to review its saved evidence, or reuse the project for a new run. Download the report you need.'
 ],result:'Your chosen workspace opens. Saved results show their owner, time and test ID.',check:'A stored result describes its saved run. Start a new run when you need current project or machine information.',page:'home'},
 {id:'bytemap',title:'ByteMap · SpinConnect packet validation',purpose:'Check SpinConnect packet layouts, offsets, variables and metadata against your B&R project.',prepare:'Have the complete Automation Studio project folder or .apj path. Add the matching metadata workbook if you want metadata comparisons.',steps:[
  'Open ByteMap and choose Machine / department.',
  'Select the project with Upload folder or Browse This PC. For a path on the application computer, enter it and click Use path.',
  'Confirm the active PLC configuration and HMI target. Select the matching workbook when required.',
  'Click Run validation and wait for the result.',
  'Open Configured packets and ByteMap. Filter by Group Code, PLC tag or finding status.',
  'Expand a finding to compare Expected and Actual, then open its source file and line. Review missing variables, datatypes, offsets, copy sizes and HMI bindings.',
  'After an approved source or mapping change, run validation again. Export the report with project and engineer details.'
 ],result:'A result with passing checks, warnings and failures, plus source locations and downloadable evidence.',check:'If a variable or HMI mapping is unresolved, confirm the selected target and workbook before editing the source.',page:'validation'},
 {id:'write-st',title:'ByteMap · Generate SpinConnect write ST',purpose:'Prepare a complete write program using project group cases and the selected HMI limits.',prepare:'Select the complete B&R project containing mms_nw_r and mms_nw_w. Confirm the active CPU configuration.',steps:[
  'In ByteMap, open the Write ST tab. Click Generate ST in the generator panel to analyze the selected project.',
  'Confirm the read routine, write routine and HMI target. If you change one, analyze again.',
  'Select the required groups, such as 130 for machine settings or 140 for process settings when those groups exist in your project.',
  'Inspect each selected group. Review writable and readonly fields, byte positions, machine conditions and layout findings.',
  'Review the HMI control, displayed limits and PLC-unit scaling. Required choices lists any parameters with multiple HMI controls; click one to select its input control. Add tighter PLC-unit limits if needed.',
  'Confirm the review checkbox and click Generate ST at the top of this panel. The generated files appear automatically. Switching tabs retains the analysis and draft for this selected project.',
  'Review the cyclic code, variable declarations and write mapping. Use Copy, Download file or Download complete ZIP.',
  'Integrate the reviewed files into the matching mms_nw_w program and compile in Automation Studio for the selected CPU.',
  'Read current settings with function 1 on the write port. Construct function 2 from the generated write field map and active variant. Check the response and read the values back.'
 ],result:'Copyable ST, matching declaration files, a complete field map and integration instructions.',check:'Read and write layouts can differ. Resolve blocked datatype/copy-size findings before generating. Re-analyze after changing project or HMI files.',page:'validation'},
 {id:'metadata',title:'MetaWorks · Prepare a SpinConnect workbook',purpose:'Create and review metadata that ByteMap and DataInspect can use.',prepare:'Select the complete B&R project and the correct machine / department in ByteMap.',steps:[
  'Click Generate metadata in ByteMap.',
  'Open MetaWorks and review parameter names, Group Codes, tag identities, datatypes, byte offsets, units and limits.',
  'Review Dropdowns for the configured values and their displayed text. Check missing or ambiguous entries.',
  'Edit the fields you intend to change and review the resulting workbook.',
  'Export Excel or CSV. Use the workbook with the matching SpinConnect project or upload it in DataInspect.'
 ],result:'An editable metadata workbook with the reviewed packet and display mappings.',check:'Use metadata for the same machine configuration and program version as the source or captured data.',page:'validation'},
 {id:'datainspect',title:'DataInspect · Read SpinConnect data',purpose:'Read and decode SpinConnect PLC packets, review values and build monitoring dashboards.',prepare:'Know the controller IP, its SpinConnect TCP port, Machine ID and matching metadata. The PLC service must be running.',steps:[
  'Open DataInspect → Manage targets. Add a target and choose Request frame → Server → B&R (SpinConnect).',
  'Enter the target name, IP address, TCP port and Machine ID. Choose the correct byte order and timeout, then Save & Apply.',
  'Load the matching metadata. Confirm the selected target before sending a request.',
  'Click Test GC 10. If it fails, read the error before continuing; check the address, service port, Machine ID and frame settings.',
  'Select a Group Code and Read Group Data, or use Test all metadata groups.',
  'Review packet status, expected and received length, decoded values, raw bytes and data-quality findings. Open the packet inspector for frame details.',
  'Open My dashboards to add displays, trends or calculations and bind each widget to a target and parameter.',
  'For automatic readings, choose live groups and an interval in Manage targets, enable live collection, then Save & Apply. Enable storage if you need historical readings.',
  'Generate Full Report to download the readings and findings with their test IDs.'
 ],result:'Current readings with their target and capture time, plus clearly marked frame or mapping failures.',check:'A failed checksum or end marker prevents trusted value decoding. Review the recommended checks in the frame explanation.',page:'plc'},
 {id:'edit-parameter',title:'DataInspect · Change a writable PLC setting',purpose:'Edit a permitted parameter and check that the PLC applied its new value.',prepare:'Use matching SpinConnect metadata with IS_WRITABLE = YES. Generate and review write_mapping.json in ByteMap for the installed project and HMI configuration.',steps:[
  'Select the intended PLC target and load its matching metadata in DataInspect.',
  'Click the pencil beside the writable parameter. Saved historical tests are read only.',
  'Load write_mapping.json from the matching ByteMap Write ST download. Confirm the project and HMI target shown.',
  'Enter the settings TCP port. Projects 2 and 5 use 21011. Select the machine configuration / write layout; conditional layouts require your explicit selection.',
  'Click Read current settings. DataInspect reads function 1 from the settings service and displays the current PLC value.',
  'Enter the new value in raw PLC units. For example, a PLC factor of 10 means 35.0 displayed units is 350 raw units. Check the displayed source limits and dropdown values.',
  'Confirm the displayed target and click Send to PLC and verify. DataInspect reads again, preserves the full group, sends the changed value, then reads it back.',
  'Wait for the verified result and test ID. If settings changed, the preview expired, or the PLC rejected the request, read current settings again and review the reported reason before another attempt.'
 ],result:'A successful write requires a valid PLC acknowledgement and matching readback. The evidence is retained in test history.',check:'The PLC keeps its machine-state and source value checks. Raw display scaling is not applied by this editor. Scalar numeric/Boolean settings are supported; YBS needs a verified settings write protocol.',page:'plc'},
 {id:'offline',title:'DataInspect · Offline captures and YBS',purpose:'Inspect captured bytes without contacting a controller, or select the YBS device profile.',prepare:'Have a complete response frame and its matching metadata. Use Chopper for a full collected log file.',steps:[
  'For a SpinConnect capture, load its workbook and open Manual received data.',
  'Choose the Group Code, Machine ID and byte order. Paste one complete decimal-byte response and click Decode and map.',
  'Review the values and any length or metadata mismatch. Export the report if needed.',
  'For a YBS device, choose Request frame → Server → YBS (Embedded C) in Manage targets and load YBS metadata.',
  'To prepare an outgoing request, open Manual Data Frame Editor & Sender, select the request frame, Machine ID and Read group code, then Generate read frame.',
  'Check the decimal and HEX preview against the intended device before Send Frame to Device. Save & Apply retains the selected frame profile.'
 ],result:'An offline decoded capture, or a correctly selected device request ready for review.',check:'Metadata and request frame must match the device. Changing between B&R and YBS requires reviewing the live groups before enabling collection again.',page:'plc'},
 {id:'matchview',title:'MatchView · Compare project revisions',purpose:'Inspect changes in logic, declarations, hardware and HMI screens.',prepare:'Have the baseline and revised Automation Studio projects.',steps:[
  'Open MatchView and select the baseline project first, then the revised project.',
  'Confirm each active PLC configuration and HMI target. Select the comparison options you need.',
  'Run comparison. Use Project View, Logic and Screen View to inspect the changes.',
  'Select a file or object. Compare added, removed and changed values on both sides.',
  'For HMI changes, open the screen and select a control to inspect its properties. For ladder changes, select a network and use zoom or Fit width.',
  'Filter to the relevant changes, review the source evidence, then export the selected report sections.'
 ],result:'A comparison with separate baseline and revised evidence and downloadable reports.',check:'Confirm project order and target selection before deciding whether a change is intended.',page:'compare'},
 {id:'logicscan',title:'LogicScan · Check engineering requirements',purpose:'Run the selected project against reviewed rules and feature pipelines.',prepare:'Have the project, machine / department and the requirements you intend to check.',steps:[
  'Open LogicScan, select the project and choose Machine / department.',
  'Choose a feature pipeline and review its enabled requirements.',
  'Run the pipeline. Filter the results by status or requirement.',
  'Open a finding to review the expected logic, actual source, variable declarations and cross references.',
  'Use Explain in Chopper when you need a source-based explanation.',
  'If you are configuring a rule, use Rule configuration, run the draft against the project, review its output, then save and enable the approved rule.',
  'Rerun the pipeline after changes and export the complete result.'
 ],result:'A saved run showing which requirements passed, failed or need review.',check:'Confirm the rule scope and accepted alternatives before deciding whether a source change is needed.',page:'rules'},
 {id:'chopper',title:'Chopper · Ask questions and decode logs',purpose:'Get explanations from projects, metadata, captured logs and reports.',prepare:'A project is optional. Attach the files relevant to your question.',steps:[
  'Open AI Assistant → Chat. Start a new chat for a separate task.',
  'Use the paperclip to attach a project, metadata workbook, log or report. You can also paste a collected log.',
  'For log decoding, attach both the log and matching metadata, then ask “Decode this log using the attached metadata.”',
  'Choose the Group Code, asset and captured time. Review decoded values, raw bytes and findings; use Simple text or Copy result to share them.',
  'For a failed frame, click Explain this capture. Read the byte positions, Expected / Received values and recommended checks.',
  'For project questions, include the program, variable, condition or symptom. Open the cited source before making a change.'
 ],result:'An answer tied to the selected files or capture, with source references and copyable results.',check:'If a required file or column is missing, attach it or refine the question rather than relying on an unrelated answer.',page:'chatbot'},
 {id:'reports',title:'Chopper · Analyze production and other reports',purpose:'Compare uploaded production, stoppage, quality, breakage, power and air-consumption records.',prepare:'Upload the reports containing the fields you want to compare.',steps:[
  'Attach the Excel reports in Chat and wait for each report to be ready.',
  'Ask for the exact measures, grouping and period: for example, “Compare machine-wise average spindle speed and delivery speed for this period.”',
  'For downtime, ask “Which machine has the highest stoppage, and what are its recorded reasons?”',
  'For several questions, list them separately or name each measure. Review the returned fields, source reports and date range.',
  'Open Split or Dashboard view. Apply the date, machine and shift filters you need.',
  'Review the charts, rankings and findings. Open worksheet references when you need the source rows.',
  'Download PDF, machine CSV or evidence JSON for the selected view.'
 ],result:'Calculated results and a dashboard based on the uploaded records and your selected question.',check:'Report uploads describe their recorded period. Check missing values and source coverage before comparing totals across different reports.',page:'chatbot'},
 {id:'virtual',title:'Virtual PLC · Run a simulated project',purpose:'Operate a supported PLC project with virtual controls and device feedback.',prepare:'Have the project and select the intended configuration.',steps:[
  'Open Virtual PLC from WorkHub or the navigation bar and import the project.',
  'Review the project configuration, task schedule and any reported blockers.',
  'Open Components or the field environment. Build devices from the project where available, then review the PLC tags, wiring and initial sensor values.',
  'Enable the field simulation to provide the intended sensor and drive feedback, then run the PLC.',
  'Operate the simulated Start / Stop controls and inspect I/O, variables, motor feedback and alarms.',
  'Pause before changing connections. Adjust editable device values, inject a fault when needed, and review the resulting alarm and recovery sequence.',
  'Save the workspace configuration to reuse it later.'
 ],result:'A running supported simulation with visible commands, feedback and project findings.',check:'PLC execution and field feedback are separate controls. Review interlocks and active alarms when a machine does not start.',page:'virtual-plc'},
 {id:'profile',title:'My profile and workspace settings',purpose:'Manage your own photo, password and workspace preferences.',prepare:'Sign in with your personal account.',steps:[
  'Click your profile photo or initials in the header, or open Settings → My profile.',
  'Choose Upload profile photo and select a PNG, JPEG or WebP up to 5 MB. Use Remove photo to return to initials.',
  'To change your password, enter the current password, new password and confirmation, then click Change password.',
  'Choose your theme and preferred table or metadata-column layout in Settings.',
  'Use Sign out when you finish, especially on a shared computer.'
 ],result:'Your saved profile photo and workspace preferences are available when you sign in again.',check:'Only Admin can enable accounts or change account roles. Password and role changes can require signing in again.',page:'settings'},
 {id:'admin',title:'Admin · Manage user access',purpose:'Approve requests and assign Admin or User access.',prepare:'Sign in with an Admin account.',steps:[
  'Open Settings → Admin settings → Workspace administration → Manage users. Review pending account requests.',
  'Enable an approved request, or choose Create user to create an account directly.',
  'Enter username, initial password, designation and company. Choose Role → User or Admin, then save.',
  'Choose Manage beside an account to change its details, role or enabled access. Leave Reset password blank to keep the current password.',
  'Save the account and tell the affected user to sign in again when their role or password changes.',
  'Disable access when the user no longer needs to sign in. Disabled accounts retain their test history.'
 ],result:'Enabled users can open every workspace feature. User management is available only to Admin.',check:'The primary Admin account remains enabled. You cannot remove your own Admin access.',page:'settings',admin:true}
];

export function UserGuide({onOpen}:{onOpen:(page:HelpDestination)=>void}){
 const {user}=useAccount();const [search,setSearch]=useState('');
 const visible=guides.filter(guide=>(!guide.admin||user.role==='admin')&&JSON.stringify(guide).toLowerCase().includes(search.trim().toLowerCase()));
 return <div className="userGuide"><div className="pageHead"><div><h1>Help · Step-by-step guides</h1><p>Choose a feature to learn what you need, how to use it, and how to review its results.</p></div></div>
  <input className="textInput" aria-label="Search help" placeholder="Search SpinConnect, metadata, reports, simulation or profile" value={search} onChange={event=>setSearch(event.target.value)}/>
  <nav className="helpContents" aria-label="Help topics"><a href="#help-frd-sample">Engineering Documentation → FRD Sample</a>{visible.map(guide=><a key={guide.id} href={'#help-'+guide.id}>{guide.title}</a>)}</nav>
  <Suspense fallback={<section className="card">Opening the engineering documentation sample…</section>}><FRDSample/></Suspense>
  <div className="helpGrid">{visible.map(guide=><section id={'help-'+guide.id} className="card helpCard" key={guide.id}><h2>{guide.title}</h2><p>{guide.purpose}</p><p className="helpPrepare"><b>Before you begin: </b>{guide.prepare}</p><h3>Steps</h3><ol>{guide.steps.map((step,index)=><li key={index}>{step}</li>)}</ol><p><b>What you will see: </b>{guide.result}</p><p className="helpAdvice"><b>Check if needed: </b>{guide.check}</p><button className="btn" onClick={()=>onOpen(guide.page)}>Open {guide.page==='home'?'WorkHub':guide.page==='settings'?'Settings':guide.page==='virtual-plc'?'Virtual PLC':guide.page==='validation'?'ByteMap':guide.page==='plc'?'DataInspect':guide.page==='compare'?'MatchView':guide.page==='rules'?'LogicScan':'Chopper'}</button></section>)}</div>
  {!visible.length&&<p role="status">No guide matches this search. Try a feature name or task.</p>}
 </div>;
}
