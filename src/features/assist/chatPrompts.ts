export const CHAT_PROMPTS=[
 {title:'Function flow',prompt:'Show a step-by-step function flow for a PLC routine in the selected project.'},
 {title:'Machine functions',prompt:'Give a clear machine summary of the selected project: machine purpose, main functions, how it works in connected sentences, communication used, supported review points and review limits. Cite sources, identify enabled tasks and label inferred behaviour.'},
 {title:'Communication',prompt:'What communication is used in this project? Trace the called blocks, task ownership, endpoints, settings and error handling with source evidence.'},
 {title:'RS485 logic',prompt:'Check the RS485 communication logic in this project. Separate physical interface from protocol; trace device/mode, block calls, status, timeout, retry and recovery. Say what is unresolved.'},
 {title:'Improvements',prompt:'Review this project for improvement candidates. Cite the observed source, explain the reason and proposed action, and distinguish possible issues from proven defects.'},
 {title:'Major differences',prompt:'What are the major differences between the two MatchView projects? Separate variable, logic, ladder, HMI layout, HMI behaviour and hardware changes.'},
 {title:'Start / stop logic',prompt:'Trace the machine start and stop conditions, interlocks and outputs in the selected project. Show the source evidence and unresolved dependencies.'},
 {title:'Alarms',prompt:'Explain alarm handling and how faults stop the machine in the selected project. Cite the logic and alarm definitions.'},
 {title:'Variable trace',prompt:'Where is <PLC_VARIABLE> declared, written and used? Trace its related logic, HMI datapoint and I/O mapping.'},
 {title:'HMI layout',prompt:'Which HMI controls changed position, size or alignment in MatchView? Show before and after values, separately from datapoint changes.'},
 {title:'Decode logs',prompt:'Decode the attached PLC log using its metadata. Show values by Group Code and list requests that failed.'},
 {title:'One ladder network',prompt:'Explain network <NUMBER> in <FILE.ld>: contacts, coils, OR branches, function blocks and the conditions that set the output.'}
];
