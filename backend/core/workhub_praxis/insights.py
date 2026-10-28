"""Personal insight layouts over existing, authorized assessment records."""
import json
from fastapi import HTTPException
from . import store,service
from .store import hub,org,identity,timestamp,text,encode

METRICS={
 'quality':('Work quality','Approval outcomes, correction feedback and actual recorded validation scores.','/100'),
 'response':('Response and follow-through','Measured correction turnaround and workflow feedback.','/100'),
 'problem_solving':('Problem solving','Short feedback captured when work is approved or completed.','/100'),
 'ownership':('Correction ownership','Resolved assigned issues divided by assigned issues in the period.','%'),
 'errors_corrected':('Errors corrected','Corrections confirmed during approval or completion.','corrections'),
 'troubleshooting_cases':('Troubleshooting cases solved','Solved cases confirmed during approval or completion.','cases'),
 'solutions_shared':('Additional solutions shared','Shared solutions outside already-published TechShare contributions.','solutions'),
 'colleagues_helped':('Colleagues helped','Contributions confirmed in project/task workflow feedback.','people'),
 'quality_cycles':('Correction iterations','Recorded request-change cycles before accepted delivery.','iterations'),
 'performance_index':('Performance Index','Delivery, quality and response from project/task outcomes; weights are shown in each profile.','/100'),
 'competency_index':('Competency Index','Quality, problem solving, correction ownership and knowledge sharing from work outcomes.','/100'),
 'competency_coverage':('Calculation coverage','Work dimensions with measured values divided by configured dimensions.','%'),
 'skill_gaps':('Skill gaps','Work capability dimensions below the configured target.','skills'),
 'completed_work':('Completed activities','Recorded completed project and task development responsibilities.','activities'),
 'development_progress':('Development progress','Completed development responsibilities divided by current project/task assignments.','%'),
 'reviewed_deliveries':('Reviewed deliveries','Work that reached authorized quality acceptance or release.','deliveries'),
 'validation_runs':('Validation activity','Recorded validation iterations. A run is not assumed to have passed.','runs'),
 'on_time_delivery':('Delivery reliability','Independently reviewed deliveries with a known preserved deadline.','%'),
 'knowledge_shared':('Knowledge sharing','Published reviewed contributions.','contributions'),
 'contribution_impact':('Contribution Impact','Available problem-solving, correction ownership and knowledge-sharing measures.','/100'),
 'document_acceptance':('Work quality','Approved work outcomes, correction feedback and recorded validation scores.','%'),
 'mom_action_closure':('MOM action closure','An approved role measurement explicitly configured as MOM action closure.','%'),
 'knowledge_reuse':('Knowledge reuse','An approved role measurement explicitly configured as Knowledge reuse.','/100'),
}
DEFAULTS=[{'id':key+'-'+view,'metric':key,'title':METRICS[key][0],'view':view,'display':display,'note':'','enabled':True}
          for key,view,display in [('performance_index','mine','card'),('competency_index','mine','card'),
                                  ('completed_work','mine','card'),('contribution_impact','mine','card'),
                                  ('performance_index','team','card'),('document_acceptance','team','card'),('mom_action_closure','team','card'),('knowledge_shared','team','card'),
                                  ('skill_gaps','team','bar'),('competency_coverage','matrix','bar'),
                                  ('on_time_delivery','reports','card'),('reviewed_deliveries','reports','card'),
                                  ('validation_runs','reports','card'),('knowledge_shared','reports','card')]]


def schema():
    store.initialize()
    with hub.db(True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS px_insight_layouts(user_id INTEGER NOT NULL,version INTEGER NOT NULL,content TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(user_id,version))')


def layout(user):
    schema();org.personal(user)
    with hub.db() as db:row=db.execute('SELECT * FROM px_insight_layouts WHERE user_id=? ORDER BY version DESC LIMIT 1',(user['id'],)).fetchone()
    return {'version':row['version'] if row else 0,'widgets':json.loads(row['content']) if row else DEFAULTS,
            'metrics':[{'id':key,'name':v[0],'description':v[1],'unit':v[2]} for key,v in METRICS.items()]}


def save(user,payload):
    schema();org.personal(user);rows=payload.get('widgets');result=[];seen=set()
    if not isinstance(rows,list) or len(rows)>40:raise HTTPException(400,'Use up to 40 insight cards.')
    for r in rows:
        if not isinstance(r,dict):raise HTTPException(400,'Provide structured insight cards.')
        key=text(r.get('id') or identity(),80,True);metric=r.get('metric');view=r.get('view');display=r.get('display','card')
        if not isinstance(metric,str) or metric not in METRICS:raise HTTPException(400,'Choose an existing insight metric.')
        if not isinstance(view,str) or view not in {'mine','team','matrix','reports'}:raise HTTPException(400,'Choose a Competency Hub section.')
        if not isinstance(display,str) or display not in {'card','bar','line','area','pie','donut','radar','gauge','heatmap','table','trend'}:raise HTTPException(400,'Choose a supported insight display.')
        if type(r.get('enabled',True))is not bool or key in seen:raise HTTPException(400,'Each card needs a unique ID and enabled status.')
        if display=='trend' and metric not in {'performance_index','competency_index'}:raise HTTPException(400,'Trends require historical approved performance or competency indices.')
        seen.add(key);result.append({'id':key,'metric':metric,'title':text(r.get('title',''),160,True),'view':view,'display':display,'note':text(r.get('note',''),2000),'enabled':r.get('enabled',True)})
    with hub.db(True) as db:
        previous=db.execute('SELECT MAX(version) FROM px_insight_layouts WHERE user_id=?',(user['id'],)).fetchone()[0] or 0
        if payload.get('version')!=previous:raise HTTPException(409,'Your insight layout changed. Reload before saving.')
        db.execute('INSERT INTO px_insight_layouts VALUES(?,?,?,?)',(user['id'],previous+1,encode(result),timestamp()))
    return layout(user)


def work_activity(user,subject,period=None):
    """Use the existing activity visibility checks; never widen their scope."""
    from backend.core.workhub_growth import performance
    try:
        # These are explicitly recent-work facts, not assessment-period scores.
        facts=performance.profile(user,subject,90)
        return {'available':True,'days':90,'indicators':facts['indicators'],'validation_results':facts.get('validation_results',[]),
                'projects':facts.get('projects',[]),'proofs':facts.get('proofs',[]),'events':facts.get('events',[])}
    except HTTPException as e:
        if e.status_code not in {403,404}:raise
        return {'available':False,'days':90,'indicators':{},'validation_results':[],'projects':[],'proofs':[],'events':[]}


def values(profile):
    actual=profile.get('work_activity',{});facts=actual.get('indicators',{});rows=profile['competencies'];assessed=[c for c in rows if c['current'] is not None]
    supported={key:next((d['value'] for d in profile['performance'] if d.get('source')==key and not d.get('not_applicable')),None) for key in ('contribution_impact','document_acceptance','mom_action_closure','knowledge_reuse')}
    result={**supported,'performance_index':profile['performance_index'],'competency_index':profile['competency_index'],
            'competency_coverage':round(100*len(assessed)/len(rows),1) if rows else None,
            'skill_gaps':sum(c['gap']>0 for c in assessed) if assessed else None,
            'completed_work':profile['experience']['completed_assignments'],
            'development_progress':profile['development_progress'],
            'reviewed_deliveries':facts.get('independently_reviewed_deliverables'),
            'validation_runs':facts.get('validation_iterations'),'on_time_delivery':facts.get('on_time_percent'),
            'knowledge_shared':facts.get('published_contributions')}
    if profile.get('work_based'):
        counts=profile['work_counts'];dims={d['id']:d['value'] for d in profile['performance']}
        from .outcomes import _mean
        result.update(completed_work=counts['completed_work'],reviewed_deliveries=counts['accepted_work'],validation_runs=counts['validation_runs'],on_time_delivery=dims['delivery'],knowledge_shared=counts['published_contributions']+counts['solutions_shared'],document_acceptance=dims['quality'],contribution_impact=_mean([dims['problem_solving'],dims['ownership'],dims['knowledge']]))
        result.update(dims);result.update(counts)
    return result
