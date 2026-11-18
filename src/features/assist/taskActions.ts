import {openDashboardBuilder} from '../workhub/dashboards/bridge';
﻿import {navigateRoute} from '../../shared/navigation';
import type {WorkspaceModule} from '../../shared/workspaceModules';
export const assistantTasks=[
 {id:'agent',name:'Investigate with validated agent',description:'Use checked source facts, read-only SQL and approved public references.',module:'assistant',category:'Analyze'},
 {id:'frd',name:'Create FRD',description:'Open a numbered requirements document draft.',module:'workhub',kind:'frd',category:'Create'},
 {id:'mom',name:'Create meeting minutes',description:'Prepare MOM, decisions and action owners.',module:'workhub',kind:'mom',category:'Create'},
 {id:'test',name:'Create validation report',description:'Prepare test cases and record actual evidence.',module:'workhub',kind:'test',category:'Create'},
 {id:'fat',name:'Create FAT document',description:'Open the factory acceptance test template.',module:'workhub',kind:'fat',category:'Create'},
 {id:'closure',name:'Create closure report',description:'Prepare handover and project closure evidence.',module:'workhub',kind:'closure',category:'Create'},
 {id:'flowchart',name:'Create flowchart / infographic',description:'Open a drawing with Text to Visual and editing tools.',module:'workhub',kind:'flowchart',category:'Create'},
 {id:'mindmap',name:'Create mind map',description:'Organize ideas in an independent diagram.',module:'workhub',kind:'mindmap',category:'Create'},
 {id:'project',name:'Create project',description:'Plan requirements, owners and dates.',module:'workhub',category:'Create'},
 {id:'dashboard',name:'Build dashboard',description:'Open the dashboard builder with your request.',module:'workhub',category:'Analyze'},
 {id:'presentations',name:'Create presentation',description:'Plan slides locally, edit the deck and export PowerPoint.',module:'assistant',category:'Create'},
 {id:'documents',name:'Compare documents',description:'Compare spreadsheets, CSV, Word or PDF files.',module:'assistant',category:'Compare'},
 {id:'compare',name:'Compare PLC revisions',description:'Open MatchView for project or PLC PDF comparisons.',module:'matchview',category:'Compare'},
 {id:'validation',name:'Validate PLC / metadata',description:'Select project inputs in ByteMap and run validation.',module:'bytemap',category:'Validate'},
 {id:'plc',name:'Inspect PLC data',description:'Open DataInspect for logs, packets and connection tools.',module:'datainspect',category:'Analyze'},
 {id:'rules',name:'Review engineering rules',description:'Open LogicScan and its evidence checks.',module:'logicscan',category:'Validate'},
 {id:'chatbot',name:'Analyze files with Chopper',description:'Open full Chat to attach spreadsheets, reports or PLC files.',module:'assistant',category:'Analyze'},
] as const;
export type AssistantTask=typeof assistantTasks[number];
let pending:{id:string;kind?:string;brief?:string}|null=null;
export function takeAssistantTask(){const value=pending;pending=null;return value;}
export function startAssistantTask(task:AssistantTask,modules:WorkspaceModule[],prompt=''){
 if(!modules.includes(task.module))throw Error('This workspace is unavailable for your account.');
 const isHub=task.module==='workhub';
 if(!navigateRoute(isHub?{page:'home'}:{page:['documents','presentations','agent'].includes(task.id)?'chatbot':task.id,assistTab:task.id==='agent'?'agent':task.id==='presentations'?'presentations':task.id==='documents'?'documents':task.id==='chatbot'?'chat':null}))return false;
 if(task.id==='dashboard'){openDashboardBuilder(prompt||'Create a dashboard');return true;}
 if(isHub){pending={id:task.id,brief:prompt.slice(0,12000),...('kind' in task?{kind:task.kind}:{})};window.dispatchEvent(new Event('usopp-assistant-task'));}
 return true;
}
export function suggestedTask(text:string){
 if(!/^\s*(please\s+)?(create|make|prepare|open|start|build|compare|validate|inspect)\b/i.test(text))return undefined;
 const id=/presentation|powerpoint|slide deck/i.test(text)?'presentations':/\bfrd\b|requirements document/i.test(text)?'frd':/\bmom\b|meeting minutes/i.test(text)?'mom':/\bfat\b/i.test(text)?'fat':/closure/i.test(text)?'closure':/validation (report|document)/i.test(text)?'test':/mind\s*map/i.test(text)?'mindmap':/flow\s*chart|infographic/i.test(text)?'flowchart':/dashboard/i.test(text)?'dashboard':/compare.*(excel|csv|spreadsheet|word|document)/i.test(text)?'documents':/compare.*plc/i.test(text)?'compare':/validate.*(plc|metadata)/i.test(text)?'validation':/create.*project/i.test(text)?'project':undefined;
 return assistantTasks.find(t=>t.id===id);
}
