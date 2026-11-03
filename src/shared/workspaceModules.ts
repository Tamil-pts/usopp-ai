/** Administrator-controlled navigation visibility. This does not grant data permissions. */
export const WORKSPACE_MODULES=[
  {id:'workhub',label:'WorkHub'},
  {id:'bytemap',label:'ByteMap'},
  {id:'datainspect',label:'DataInspect'},
  {id:'logicscan',label:'LogicScan'},
  {id:'matchview',label:'MatchView'},
  {id:'virtual_plc',label:'Virtual PLC'},
  {id:'edesign',label:'e-design'},
  {id:'assistant',label:'AI Assistant'},
] as const;
export type WorkspaceModule=typeof WORKSPACE_MODULES[number]['id'];
export const ALL_WORKSPACE_MODULES:WorkspaceModule[]=WORKSPACE_MODULES.map(module=>module.id);
export const PAGE_MODULES={home:'workhub',validation:'bytemap',plc:'datainspect',compare:'matchview',circuit:'edesign',electrical:'edesign',rules:'logicscan',edesign:'edesign',chatbot:'assistant'} as const;
export function visibleModules(user:{role:string;workspaceModules?:WorkspaceModule[]}):WorkspaceModule[]{
  return user.role==='admin'?ALL_WORKSPACE_MODULES:(user.workspaceModules??ALL_WORKSPACE_MODULES);
}
