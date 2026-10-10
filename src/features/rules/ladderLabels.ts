export const networkName=(network:any,index:number)=>network.label?.trim()||`Network check ${index+1}`;
export function networkOrder(network:any,index:number,networks:any[]):string{
 const name=networkName(network,index);
 if(!network.relation||network.relation==='presence')return `${name}: must be present. No additional order constraint; another check may refer to this network.`;
 const target=networks.findIndex(other=>other.id===network.relativeTo);
 if(target<0)return `${name}: choose or add the other network to define which must come first.`;
 const other=networkName(networks[target],target);
 const before=network.relation.endsWith('before');
 return `${before?name:other} must come ${network.relation.startsWith('immediately')?'immediately ':''}before ${before?other:name}. First: ${before?name:other}. Then: ${before?other:name}.`;
}
