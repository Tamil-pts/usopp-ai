import {useState} from 'react';
import {Copy} from 'lucide-react';
import {copyChatText} from '../assist/chatFiles';

export type ExplanationParagraph={stepId:string;sequenceId:string;number:number;sequenceTitle:string;title:string;text:string;sourceFile:string;line:number;endLine:number};
export type WorkingExplanationData={intro:string;paragraphs:ExplanationParagraph[];notes:string[]};

export function explanationText(value:WorkingExplanationData){
 return [value.intro,...value.paragraphs.map(item=>item.text),...value.notes].join('\n\n');
}

export function WorkingExplanation({value,selectedStepId,onSelect,compact=false}:{value:WorkingExplanationData;selectedStepId?:string;onSelect?:(paragraph:ExplanationParagraph)=>void;compact?:boolean}){
 const [copyNotice,setCopyNotice]=useState('');
 return <details className={`flowWorkingExplanation ${compact?'compact':''}`} open>
  <summary>How this subroutine works</summary>
  <div className="flowExplanationIntro"><p>{value.intro}</p><button type="button" className="btn" onClick={()=>void copyChatText(explanationText(value)).then(ok=>setCopyNotice(ok?'Explanation copied.':'Select the explanation and copy it manually.'))}><Copy size={14}/> Copy explanation</button></div>
  {copyNotice&&<small role="status">{copyNotice}</small>}
  <div className="flowExplanationParagraphs">{value.paragraphs.map((item,index)=><article key={`${item.sequenceId}-${item.stepId}-${index}`} className={selectedStepId===item.stepId?'selected':''}><p>{item.text}</p>{onSelect?<button type="button" className="flowExplanationStep" onClick={()=>onSelect(item)}>{item.sequenceTitle} · Step {item.number} · {item.title}</button>:<small>{item.sequenceTitle} · Step {item.number}</small>}</article>)}</div>
  {value.notes.map((note,index)=><p className="flowExplanationNote" key={index}>{note}</p>)}
 </details>;
}
