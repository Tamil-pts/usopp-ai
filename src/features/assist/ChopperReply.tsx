import type {ReactNode} from 'react';

/** Render the answer's basic formatting as React text, with no HTML evaluation. */
export function ChopperReply({text,onReference}:{text:string;onReference?:(id:string)=>void}) {
 const inline=(value:string):ReactNode[]=>value.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[SH]\d+\])/g).map((part,index)=>{
  if(part.startsWith('**')&&part.endsWith('**'))return <strong key={index}>{part.slice(2,-2)}</strong>;
  if(part.startsWith('`')&&part.endsWith('`'))return <code key={index}>{part.slice(1,-1)}</code>;
  if(/^\[[SH]\d+\]$/.test(part)&&onReference)return <button className="chopperCitation" key={index} onClick={()=>onReference(part.slice(1,-1))} aria-label={`Show source ${part.slice(1,-1)}`}>{part}</button>;
  return part;
 });
 const lines=text.replace(/\r\n/g,'\n').split('\n'),blocks:ReactNode[]=[];
 const cells=(line:string)=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(cell=>cell.trim());
 const separator=(line:string)=>/^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
 for(let i=0;i<lines.length;){
  const key=i,line=lines[i];
  if(!line.trim()){i++;continue;}
  if(/^\s*```/.test(line)){
   const code:string[]=[];i++;
   while(i<lines.length&&!/^\s*```/.test(lines[i]))code.push(lines[i++]);
   if(i<lines.length)i++;
   blocks.push(<pre key={key}><code>{code.join('\n')}</code></pre>);continue;
  }
  const heading=/^\s*#{1,4}\s+(.+)$/.exec(line);
  if(heading){blocks.push(<h3 key={key}>{inline(heading[1])}</h3>);i++;continue;}
  if(line.includes('|')&&i+1<lines.length&&separator(lines[i+1])){
   const headers=cells(line),rows:string[][]=[];i+=2;
   while(i<lines.length&&lines[i].trim()&&lines[i].includes('|'))rows.push(cells(lines[i++]));
   blocks.push(<div className="chopperReplyTable" key={key}><table><thead><tr>{headers.map((cell,j)=><th key={j}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row,j)=><tr key={j}>{headers.map((_,k)=><td key={k}>{inline(row[k]||'')}</td>)}</tr>)}</tbody></table></div>);continue;
  }
  if(/^\s*[-*]\s+/.test(line)){
   const items:string[]=[];
   while(i<lines.length&&/^\s*[-*]\s+/.test(lines[i]))items.push(lines[i++].replace(/^\s*[-*]\s+/,''));
   blocks.push(<ul key={key}>{items.map((item,j)=><li key={j}>{inline(item)}</li>)}</ul>);continue;
  }
  const paragraph:string[]=[line];i++;
  while(i<lines.length&&lines[i].trim()&&!/^\s*(?:#{1,4}\s|[-*]\s|```)/.test(lines[i])&&!(lines[i].includes('|')&&i+1<lines.length&&separator(lines[i+1])))paragraph.push(lines[i++]);
  blocks.push(<p key={key}>{inline(paragraph.join('\n'))}</p>);
 }
 return <div className="chopperReply">{blocks}</div>;
}
