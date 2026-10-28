import {userStorage} from './userStorage';
export type ProjectTool='bytemap'|'matchview'|'datainspect';
export const toolProjectKey=(tool:ProjectTool)=>'usopp_workhub_tool_project_'+tool;
export function toolProjectHeaders(tool:ProjectTool):Record<string,string>{
 try{const saved=JSON.parse(userStorage.getItem(toolProjectKey(tool))||'{}');return {'X-WorkHub-Project':saved.enabled!==false&&saved.project_id?saved.project_id:'-'};}catch{return {'X-WorkHub-Project':'-'};}
}
