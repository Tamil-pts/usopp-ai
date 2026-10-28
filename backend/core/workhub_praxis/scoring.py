"""Shared pure calculations for dashboards, details and report exports."""
import math


def weighted(values,method='weighted_mean'):
    if not values:return None
    if method=='minimum':return round(min(v for v,w in values),2)
    if method=='weighted_geometric':
        if any(v==0 for v,w in values):return 0
        return round(math.exp(sum(w*math.log(v) for v,w in values)/sum(w for v,w in values)),2)
    return round(sum(v*w for v,w in values)/sum(w for v,w in values),2)


def calculate(model,content,definitions):
    levels=content.get('competencies',{});performance=content.get('performance',{})
    competency_rows=[];performance_rows=[];cv=[];pv=[];missing_c=0;missing_p=0
    for binding in model.get('competencies',[]):
        definition=definitions.get(binding['competency_id'],{})
        entered=levels.get(binding['competency_id'],{});current=entered.get('level')
        if current is None:missing_c+=1
        else:cv.append((current/5*100,binding['weight']))
        competency_rows.append({'id':binding['competency_id'],'name':definition.get('name','Archived competency'),
            'category':definition.get('category',''),'description':definition.get('description',''),'criteria':definition.get('criteria',''),
            'current':current,'required':binding['required_level'],'gap':max(0,binding['required_level']-current) if current is not None else None,
            'weight':binding['weight'],'note':entered.get('note',''),'references':entered.get('references') or content.get('references',[]),
            'review_frequency_days':definition.get('review_frequency_days',90)})
    for dimension in model.get('performance',[]):
        entered=performance.get(dimension['id'],{});value=entered.get('value');na=entered.get('not_applicable',False)
        if value is None and not na:missing_p+=1
        elif not na:pv.append((value,dimension['weight']))
        performance_rows.append({**dimension,'value':value,'not_applicable':na,'note':entered.get('note',''),'references':entered.get('references') or content.get('references',[])})
    return {'performance_index':None if missing_p else weighted(pv,model.get('method')),
            'competency_index':None if missing_c else weighted(cv),
            'performance_status':'Insufficient Data' if missing_p and pv else 'Not Assessed' if not pv else 'Assessed',
            'competency_status':'Insufficient Data' if missing_c and cv else 'Not Assessed' if not cv else 'Assessed',
            'competencies_assessed':len(cv),'competencies_required':len(model.get('competencies',[])),
            'competencies':competency_rows,'performance':performance_rows,
            'methodology':{'performance':model.get('method','weighted_mean'),'competency':'Weighted mean of approved proficiency / 5 × 100',
                'missing':'Missing values are unassessed. Not-applicable performance dimensions are excluded with a recorded reason. No score is subtracted for missing work or records.'}}
