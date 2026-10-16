export type EngineeringFeature='validation'|'plc'|'compare'|'rules'|'chatbot';
export const FEATURES:Record<EngineeringFeature,{name:string;purpose:string;steps:string[];recommendation:string}>={
  validation:{name:'ByteMap',purpose:'Inspect PLC packet layouts, metadata, HMI mappings and generated workbooks.',steps:[
    'Select or upload the Automation Studio project and confirm the machine/department and active configuration.',
    'Run the packet checks. Metadata is optional; upload it when you want a workbook comparison.',
    'Expand a warning or failure for TAG_CODE, Group Code, file, line, expected value and suggested fix.',
    'Open MetaWorks to generate metadata, review both worksheets and export the workbook. Rerun checks after a source or mapping change.'
  ],recommendation:'Start with the earliest incorrect packet offset. Check the source write size and nw_i increment, then compare the payload-relative offset, datatype and Sheet2 mappings.'},
  plc:{name:'DataInspect',purpose:'Read live PLC packets and verify their decoded values against metadata.',steps:[
    'Open Manage targets. Choose the machine/department and Real PLC, Automation Studio simulation or Data simulator.',
    'For a real target, enter the controller IP, its TCP server port, Machine ID, byte order and timeout. Use GC 10 Test, then Save & Apply.',
    'Load the machine metadata, select a Group Code or Run All, and inspect values, offsets and packet findings.',
    'Use My dashboards for personal live/report layouts and formulas. Enable server collection and optional storage per target; it starts disabled and retains at most 30 days. Confirm the active target before Manual Frame or RTC writes.'
  ],recommendation:'If GC 10 fails, resolve the connection or frame error before checking other groups. If it passes, compare payload length, byte order, offsets and scale factors with the selected machine metadata.'},
  compare:{name:'MatchView',purpose:'Trace changes between two Automation Studio project revisions.',steps:[
    'Choose the baseline project and the revised project in the correct order.',
    'Confirm both machine types, active PLC configurations and HMI targets.',
    'Run comparison and inspect added, removed and modified files plus individual source differences.',
    'Export HTML or PDF with the engineer cover details. Check the revised project in ByteMap or LogicScan before approving changes.'
  ],recommendation:'Confirm the baseline/revised order and active targets first. Review changed logic and declarations together; a textual difference alone does not establish an engineering defect.'},
  rules:{name:'LogicScan',purpose:'Run feature pipelines against configured engineering requirements.',steps:[
    'Select the project and machine/department, then create or open a feature pipeline.',
    'Configure rules and feature links in AI Assistant → KnowHub → Rule Library.',
    'Run the pipeline. Expand failed checks for the named rule, selected file, accepted configurations and cross-reference evidence.',
    'Use AI Assistant to explain a finding or add an approved alternative. Test the draft, save and enable it, then rerun the pipeline.',
    'Open ResultView and export the complete run as HTML or PDF. Enter the project name, description, validated by, validation details, approved by and date for the cover.'
  ],recommendation:'Separate a wrong requirement from a source defect. Check the target file, accepted alternative and every cross-reference before teaching; add approved alternatives without replacing the original.'},
  chatbot:{name:'AI Assistant',purpose:'Explain findings, configure requirements and maintain engineering knowledge.',steps:[
    'Ask Chopper about any uSOPp feature. A selected project is optional; use its evidence when discussing project findings.',
    'Use the chat paperclip to attach a collected PLC log and metadata, or paste the log. Read and copy decoded tables directly in chat.',
    'Include the relevant file, PLC tag, datatype, Group Code and expected behaviour.',
    'Configure requirements, accepted alternatives and cross-references; run the draft against the selected project.',
    'Review source evidence before saving knowledge. Use KnowHub to view, edit, duplicate and manage saved rules.'
  ],recommendation:'Keep explanations tied to the exact file, tag and active target. Treat suggested changes as proposals until the evidence and draft checks confirm them.'}
};
