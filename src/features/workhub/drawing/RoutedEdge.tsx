import {BaseEdge,EdgeLabelRenderer,type EdgeProps} from '@xyflow/react';
import type {Row} from '../intelligence/api';
export function RoutedEdge({sourceX,sourceY,targetX,targetY,data,markerEnd,style,label}:EdgeProps){
 const points=(data as Row)?.waypoints||[],path=`M${sourceX} ${sourceY} `+points.map((p:Row)=>`L${p.x} ${p.y}`).join(' ')+` L${targetX} ${targetY}`;
 return <><BaseEdge path={path} markerEnd={markerEnd} style={style}/>{label&&<EdgeLabelRenderer><div className="drawing-edge-label" style={{position:'absolute',transform:`translate(-50%,-50%) translate(${(sourceX+targetX)/2}px,${(sourceY+targetY)/2-12}px)`,pointerEvents:'none',fontSize:12,background:'var(--panel)',color:'var(--text)'}}>{String(label)}</div></EdgeLabelRenderer>}</>;
}
