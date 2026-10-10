const names:Record<string,string>={check:'Check',file:'Source file',line:'Line',groupCode:'Group Code',actual:'Actual result',expected:'Expected',property:'Property',properties:'Property checks',acceptedConfiguration:'Accepted configuration',matchedAlternative:'Matched alternative',declarationText:'Variable declarations',declarationFile:'Declaration file',nameMatch:'Object name matching',classId:'Class ID',textGroupFile:'Text group file',referenceChecks:'Referenced HMI checks',characterRequirement:'Allowed characters',shiftLevels:'Shift levels',nameOverride:'Referenced object',searchedFiles:'Files searched',notRequiredReason:'Why this alternative is not required'};
const label=(key:string)=>names[key]||key.replace(/([a-z])([A-Z])/g,'$1 $2').replaceAll('_',' ').replace(/^./,letter=>letter.toUpperCase());

export function FindingValue({value}:{value:any}){
 if(value===null||value===undefined||value==='')return <span className="muted">Not available</span>;
 if(Array.isArray(value))return <div className="findingValues">{value.map((entry,index)=><section key={index}>{value.length>1&&<small>Item {index+1}</small>}<FindingValue value={entry}/></section>)}</div>;
 if(typeof value==='object')return <table className="findingValueTable"><tbody>{Object.entries(value).filter(([,entry])=>entry!==undefined&&entry!==null&&entry!=='').map(([key,entry])=><tr key={key}><th>{label(key)}</th><td><FindingValue value={entry}/></td></tr>)}</tbody></table>;
 const source=String(value);
 return /[\n\r]|:=|<Property\b|memcpy\s*\(/.test(source)?<pre className="findingSource">{source.trim()}</pre>:<span>{source}</span>;
}

export function ReadableFindings({rows,onSource,onAcceptHmiActual}:{rows:any[];onSource?:(file:string,line:number,edit:boolean)=>void;onAcceptHmiActual?:(finding:any,attempt:any,property:any)=>void}){
 return <section className="readableFindings">{rows.map((entry,index)=>{
  const row=typeof entry==='object'&&entry!==null?entry:{actual:String(entry)};
  const optional=row.status==='NOT_REQUIRED';
  const result=optional?'Alternative not required':row.status==='PASS'?'Passed':row.status==='FAIL'||row.status==='MISSING'?'Failed':row.status||'Finding';
  const explanation=optional?row.notRequiredReason:row.status==='PASS'?'The required configuration matched in the source shown below.':row.actual==='No complete accepted source block found'?'The required source block was not found in this file and Group Code. Check the expected code and configured file.':undefined;
  return <article className={'readableFinding '+(row.status||'INFO')} key={index}>
   <header><h4>{row.check||row.name||`Finding ${index+1}`}{row.groupCode!==undefined&&row.groupCode!==null?` · Group ${row.groupCode}`:''}</h4><b>{result}</b></header>
   {row.file&&<p><b>Where:</b> {row.file}{row.line?` · line ${row.line}`:''}{row.control?` · object ${row.control}`:''}</p>}
   {row.acceptedConfiguration&&<p>{row.acceptedConfiguration===1?'Primary configuration':`Accepted configuration ${row.acceptedConfiguration-1}`}</p>}
   {row.matchedAlternative&&<p>Matched complete alternative {row.matchedAlternative}.</p>}
   {explanation&&<p>{explanation}</p>}
   {row.properties&&<PropertyFindings rows={row.properties}/>}
   {row.actual!==undefined&&<section><b>{row.status==='PASS'?'Matched source / result':'Actual result'}</b>{row.attempts?.length?<p>{row.attempts.length} object/configuration attempt(s) checked. The failed property checks are shown below.</p>:<FindingValue value={row.actual}/>}</section>}
   {row.expected!==undefined&&<details open={row.status==='FAIL'||row.status==='MISSING'}><summary>What was expected</summary><FindingValue value={row.expected}/></details>}
   {row.ladderNetworks&&<section><h5>Ladder network checks</h5><FindingValue value={row.ladderNetworks}/></section>}
   {row.attempts?.map((attempt:any,i:number)=><details key={i} open={attempt.status==='FAIL'}><summary>{attempt.control||'Object'} · configuration {attempt.alternative||i+1} · {attempt.status}</summary>{attempt.reason&&<p>{attempt.reason}</p>}{attempt.properties&&<PropertyFindings rows={attempt.properties} onAccept={onAcceptHmiActual?property=>onAcceptHmiActual(row,attempt,property):undefined}/>} {attempt.availableObjects&&<details><summary>Objects found in this file</summary><FindingValue value={attempt.availableObjects}/></details>}</details>)}
   {(row.suggestedFix||row.recommendations)&&<aside className="findingRecommendation"><b>Recommended action</b><FindingValue value={row.suggestedFix||row.recommendations}/></aside>}
   {!row.suggestedFix&&!row.recommendations&&!optional&&(row.status==='FAIL'||row.status==='MISSING')&&<aside className="findingRecommendation"><b>Recommended action</b><p>{String(row.actual||'').includes('not found')?'Check the configured file path and target scope, then compare the expected requirement with the project source.':'Correct the failed properties or source logic shown above. If the project uses another approved configuration, add it as a complete alternative and rerun this rule.'}</p></aside>}
   {row.searchedFiles?.length>0&&<details><summary>Files searched</summary><FindingValue value={row.searchedFiles}/></details>}
   {onSource&&row.file&&!row.file.includes(', ')&&<button className="btn" onClick={()=>onSource(row.file,Number(row.line)||1,false)}>View source</button>}
  </article>;
 })}</section>;
}

function PropertyFindings({rows,onAccept}:{rows:any[];onAccept?:(row:any)=>void}){
 return <div className="findingTableWrap"><table><thead><tr><th>Property checked</th><th>Expected</th><th>Actual</th><th>Result</th>{onAccept&&<th>Teach rule</th>}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}><td>{row.property}</td><td><FindingValue value={row.expected}/></td><td><FindingValue value={row.actual}/></td><td>{row.status==='PASS'?'Passed':'Failed'}</td>{onAccept&&<td>{row.status==='FAIL'&&row.actual!==null&&row.actual!==undefined&&<button type="button" className="btn" onClick={()=>onAccept(row)}>Accept actual as HMI alternative</button>}</td>}</tr>)}</tbody></table></div>;
}
