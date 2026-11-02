// Standalone report preferences live only in this document, with no account API.
const values=new Map<string,string>();
export const userStorage={getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value)}};
