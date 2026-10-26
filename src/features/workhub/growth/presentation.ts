/** Display copy only. Assessment rules and recorded values remain server-owned. */
export const CAPABILITY_COPY:Record<string,{title:string;description:string}>={
  problem_solving:{title:'Problem Solving',description:'Investigating causes and resolving engineering problems through reviewed work.'},
  work_quality:{title:'Work Quality',description:'Delivering accurate, complete work that meets the recorded review criteria.'},
  execution:{title:'Execution',description:'Following through on planned engineering tasks and delivering reviewed outcomes.'},
  ownership:{title:'Ownership',description:'Taking responsibility for delivery, handover and requested corrections.'},
  knowledge_sharing:{title:'Knowledge Sharing',description:'Publishing reviewed solutions, project knowledge and reusable methods.'},
};

export const isUntitledContribution=(value:unknown)=>typeof value!=='string'||!value.trim()||/^(not specified|new engineering contribution|engineering contribution|untitled contribution)$/i.test(value.trim());
export const contributionTitle=(value:unknown)=>isUntitledContribution(value)?'Untitled contribution':String(value).trim();
export const countLabel=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString():'—';

export const RECORD_LABELS:Record<string,string>={
  draft:'Draft',submitted:'Submitted',approved:'Approved',rejected:'Returned for correction',published:'Published',
  reviewed_evidence:'Reviewed work',independent_review:'Independently reviewed',native_result:'Recorded result',
  recorded:'Recorded activity',recorded_feedback:'Review feedback',self_review:'Self reviewed',
  attribution_missing:'Attribution not recorded',time_review_only:'Time entry reviewed',
  manual:'Submitted work',article:'Knowledge article',event:'Project delivery',
  library_search:'Library search',source_excerpts:'Published sources',local_ai:'Internal explanation',
};
