import {Bot} from 'lucide-react';
import {FEATURES,type EngineeringFeature} from './features';
export function FeatureRecommendation({feature,projectReady,hasResult,failures=0,warnings=0}:{feature:EngineeringFeature;projectReady:boolean;hasResult:boolean;failures?:number;warnings?:number}){
  const config=FEATURES[feature];
  let next=config.recommendation;
  if(['validation','rules'].includes(feature)&&!projectReady)next='Select the project and machine/department first. Confirm the active configuration before running checks.';
  else if(feature==='validation'&&hasResult)next=failures?`${failures} failed check(s): open the first failure and follow its file/line evidence. Fix the source cause before checking downstream offsets. ${config.recommendation}`:warnings?`${warnings} warning(s) need review. Confirm unresolved declarations and HMI mappings from source evidence, then rerun the checks.`:'The latest packet run has no failed checks. Review any excluded scopes and export the report before approving the result.';
  else if(feature==='compare'&&!hasResult)next='Choose the baseline and revised projects, confirm their active configurations, then run the comparison. '+next;
  return <aside className="featureRecommendation" aria-label={`${config.name} recommendations`}><Bot size={24}/><div><b>Chopper · {config.name}</b><p>{next}</p></div></aside>;
}
