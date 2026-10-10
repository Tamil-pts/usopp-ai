import {userStorage} from './userStorage';
import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
type Layout={mode:'auto'|'fit'|'custom';width:number};
const Context=createContext<{layout:Layout;setLayout:(value:Layout)=>void}>({layout:{mode:'auto',width:160},setLayout:()=>{}});
export const useTableLayout=()=>useContext(Context);
export function TableLayoutProvider({children}:{children:ReactNode}) {
  const [layout,setLayout]=useState<Layout>(()=>{try{const v=JSON.parse(userStorage.getItem('usopp_table_layout')||'null');return v&&['auto','fit','custom'].includes(v.mode)?{mode:v.mode,width:Math.max(80,Math.min(400,Number(v.width)||160))}:{mode:'auto',width:160}}catch{return {mode:'auto',width:160}}});
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    userStorage.setItem('usopp_table_layout',JSON.stringify(layout));
    const root=ref.current;if(!root)return;
    const size=()=>root.querySelectorAll<HTMLTableElement>('table').forEach(table=>{
      const bodyRows=Array.from(table.tBodies).flatMap(b=>Array.from(b.rows).slice(0,5));
      const count=Math.max(1,...bodyRows.map(r=>Array.from(r.cells).reduce((n,c)=>n+c.colSpan,0)),...Array.from(table.tHead?.rows||[]).map(r=>Array.from(r.cells).reduce((n,c)=>n+c.colSpan,0)));
      table.style.setProperty('--table-min-width',layout.mode==='fit'?'0px':`${count*(layout.mode==='custom'?layout.width:100)}px`);
    });
    size();const observer=new MutationObserver(size);observer.observe(root,{childList:true,subtree:true});return()=>observer.disconnect();
  },[layout]);
  return <Context.Provider value={{layout,setLayout}}><div ref={ref} className="tableLayoutRoot" data-table-layout={layout.mode}>{children}</div></Context.Provider>;
}
