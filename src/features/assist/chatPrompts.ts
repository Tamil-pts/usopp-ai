export const CHAT_PROMPTS=[
 {title:'Machine functions',prompt:'Explain the machine functions and operating sequence of the selected project. Cite source files and ladder networks; identify active tasks and inferred behaviour.'},
 {title:'Major differences',prompt:'What are the major differences between the two MatchView projects? Separate variable, logic, ladder, HMI layout, HMI behaviour and hardware changes.'},
 {title:'Start / stop logic',prompt:'Trace the machine start and stop conditions, interlocks and outputs in the selected project. Show the source evidence and unresolved dependencies.'},
 {title:'Alarms',prompt:'Explain alarm handling and how faults stop the machine in the selected project. Cite the logic and alarm definitions.'},
 {title:'Variable trace',prompt:'Where is <PLC_VARIABLE> declared, written and used? Trace its related logic, HMI datapoint and I/O mapping.'},
 {title:'HMI layout',prompt:'Which HMI controls changed position, size or alignment in MatchView? Show before and after values, separately from datapoint changes.'},
 {title:'Decode logs',prompt:'Decode the attached PLC log using its metadata. Show values by Group Code and list requests that failed.'},
 {title:'One ladder network',prompt:'Explain network <NUMBER> in <FILE.ld>: contacts, coils, OR branches, function blocks and the conditions that set the output.'}
];
