"""Guided engineering contributions, immutable revisions and reviewed publication."""
from collections import Counter
import json
import re
from fastapi import HTTPException
from . import store
from .store import hub,identity,timestamp,text,encode

QUESTIONS={
 'troubleshooting':[
  ('symptom','What error or unexpected behaviour did you encounter?',[]),
  ('environment','Where did it happen? Include the machine, software or circuit details that matter.',[]),
  ('investigation','What did you check or try, and what did you observe?',[]),
  ('root_cause','What was the root cause?',['Confirmed from evidence','Suspected; not yet confirmed','Not identified']),
  ('solution','What solution or workaround did you apply?',[]),
  ('verification','How did you check the result?',['Tested with supporting evidence','Reviewed by a colleague','Not yet verified']),
  ('reuse','What should another engineer check before reusing this solution?',[])],
 'project_knowledge':[
  ('purpose','What project knowledge would you like to share?',[]),
  ('context','Which system, machine or project context does it apply to?',[]),
  ('method','Describe the sequence, design or method another engineer should understand.',[]),
  ('details','Which parameters, interfaces, documents or technical details are essential?',[]),
  ('verification','How was this knowledge checked?',['Reviewed against project evidence','Demonstrated in the project','Not yet verified']),
  ('reuse','Where can it be reused, and what are its limitations?',[])],
 'solutions':[
  ('problem','What engineering problem or improvement opportunity did you address?',[]),
  ('before','What was the previous behaviour or method?',[]),
  ('solution','Describe the technical solution and how to implement it.',[]),
  ('result','What changed? Include measurements only if recorded.',['Measured improvement available','Qualitative improvement only','Result not yet measured']),
  ('verification','How did you verify the change?',['Tested with supporting evidence','Reviewed by a colleague','Not yet verified']),
  ('reuse','What dependencies, risks or limitations should another engineer know?',[])],
 'research':[
  ('question','What engineering question were you investigating?',[]),
  ('sources','Which documents, experiments or references did you use?',[]),
  ('findings','What did you learn or establish?',[]),
  ('experiments','What did you try, and what results did you observe?',[]),
  ('verification','What is the confidence of the findings?',['Supported by experiments or references','Preliminary findings','Still under investigation']),
  ('application','How could this help a project, and what remains unanswered?',[])],
 'best_practices':[
  ('scope','What recurring engineering activity does this method improve?',[]),
  ('method','Describe the reusable method, checklist or best practice.',[]),
  ('steps','What steps should another engineer follow?',[]),
  ('verification','What evidence supports this method?',['Used successfully with evidence','Peer-reviewed method','Proposed; not yet verified']),
  ('limits','When should this method be adapted or avoided?',[]),
  ('reuse','What files, references or examples help someone reuse it?',[])]}


def keywords(title,answers,provided=None):
    if provided is not None:
        if not isinstance(provided,list) or len(provided)>25:raise HTTPException(400,'Use up to 25 keywords.')
        return list(dict.fromkeys(text(str(value),60,True).casefold() for value in provided))
    stop={'this','that','with','from','what','when','then','were','have','been','into','only','used','project','engineering','the','and','for','not','yet','was','are','you','your'}
    words=re.findall(r'[\w][\w.+#-]{2,50}',title+' '+' '.join(str(value) for value in answers.values()),re.UNICODE)
    return [key for key,_ in Counter(word.casefold() for word in words if word.casefold() not in stop).most_common(12)]


def structured(category,title,answers):
    lines=['# '+title,'','Category: '+store.CATEGORIES[category],'']
    for key,question,_ in QUESTIONS[category]:
        value=answers.get(key)
        if value:lines.extend(['## '+question,str(value),''])
    return '\n'.join(lines).strip()


def save(user,payload,key=None):
    store.initialize();store.personal(user)
    with hub.db(True) as db:
        obj=store.object_row(db,'article',key) if key else None
        if obj:
            store.author(user,obj)
            if payload.get('version')!=obj['current_revision']:raise HTTPException(409,'This article changed. Refresh before saving a new revision.')
        project_id,task_id=store.project_link(db,user,payload.get('project_id') or None,payload.get('task_id') or None,contribute=True)
        if obj and (obj['published_revision'] or obj['approved_revision']) and (obj['project_id']!=project_id or obj['task_id']!=task_id):raise HTTPException(409,'Keep the approved article project/task link. Create a separate contribution for another project.')
        category=payload.get('category','troubleshooting')
        if not isinstance(category,str) or category not in QUESTIONS:raise HTTPException(400,'Choose a contribution category.')
        answers=payload.get('answers',{})
        if not isinstance(answers,dict) or any(key not in {q[0] for q in QUESTIONS[category]} for key in answers):raise HTTPException(400,'Provide answers for this contribution type.')
        answers={key:text(value,6000) for key,value in answers.items()}
        suggested=next((value for value in answers.values() if value.strip()),'New engineering contribution').splitlines()[0][:150]
        title=text(payload.get('title') or suggested,180,True);body=text(payload.get('body') or structured(category,title,answers),100000)
        tags=keywords(title,answers,payload.get('keywords'))
        now=timestamp();key=key or identity()
        if not obj:db.execute('INSERT INTO cp_articles(id,author_id,project_id,task_id,created_at,updated_at) VALUES(?,?,?,?,?,?)',(key,user['id'],project_id,task_id,now,now))
        files=store.owned_files(db,user,'article',key,payload.get('file_ids',[]))
        number=db.execute('SELECT COALESCE(MAX(number),0)+1 FROM cp_revisions WHERE article_id=?',(key,)).fetchone()[0];revision=identity()
        db.execute('INSERT INTO cp_revisions(id,article_id,number,title,category,keywords,answers,body,file_ids,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(revision,key,number,title,category,encode(tags),store.bounded(answers),body,encode(files),now))
        db.execute('UPDATE cp_articles SET project_id=?,task_id=?,current_revision=?,updated_at=? WHERE id=?',(project_id,task_id,revision,now,key))
        store.action(db,user,'article',key,revision,'draft_saved')
        return {'id':key,'revision_id':revision,'number':number}


def visible(db,user,obj,rev):
    if obj['author_id']==user['id'] or user['role']=='admin':return True
    return bool(rev['status']=='published' and rev.get('published_at')) or rev['reviewer_id']==user['id'] and rev['status']!='draft'


def detail(user,key,revision_id=None):
    store.initialize()
    with hub.db() as db:
        obj=store.object_row(db,'article',key);store.require_read(db,user,'article',obj)
        revisions=[store.revision(db,'article',r['id'],key) for r in db.execute('SELECT id FROM cp_revisions WHERE article_id=? ORDER BY number DESC',(key,))]
        allowed=[rev for rev in revisions if visible(db,user,obj,rev)]
        selected=next((rev for rev in allowed if rev['id']==revision_id),None) if revision_id else allowed[0] if allowed else None
        if not selected:raise HTTPException(403,'This article revision is not available to your account.')
        ids={key for rev in allowed for key in rev['file_ids']}
        files=[dict(row) for row in db.execute("SELECT * FROM cp_files WHERE object_type='article' AND object_id=?",(key,)) if row['id'] in ids or obj['author_id']==user['id'] or user['role']=='admin']
        return {'article':obj,'revision':selected,'revisions':[r for r in allowed], 'files':files,
                'reviewers':store.reviewers(db,obj['project_id'],obj['author_id']) if obj['author_id']==user['id'] or user['role']=='admin' else [],
                'history':[dict(r) for r in db.execute("SELECT * FROM cp_actions WHERE object_type='article' AND object_id=? ORDER BY created_at DESC",(key,)) if r['revision_id'] in {rev['id'] for rev in allowed}]}


def review(user,key,payload):
    store.initialize();store.personal(user)
    with hub.db(True) as db:
        obj=store.object_row(db,'article',key);rev=store.revision(db,'article',payload.get('revision_id'),key)
        if obj['current_revision']!=rev['id']:raise HTTPException(409,'A newer article revision exists. Review the latest revision.')
        action=payload.get('action');comment=text(payload.get('comment',''),4000);now=timestamp()
        if action=='submit':
            store.author(user,obj)
            if rev['status']!='draft':raise HTTPException(409,'Save a new draft revision before resubmitting.')
            if len(rev['body'].strip())<40 or not rev['answers']:raise HTTPException(400,'Answer the guided questions and review a useful article before submitting.')
            required={'troubleshooting':('symptom','solution'),'project_knowledge':('purpose','method'),'solutions':('problem','solution'),'research':('question','findings'),'best_practices':('scope','method')}[rev['category']]
            if any(not rev['answers'].get(field) or rev['answers'][field]=='Not specified' for field in required):raise HTTPException(400,'Complete the main problem/purpose and solution/findings before submitting the article.')
            reviewer=store.review_user(db,obj['project_id'],obj['author_id'],payload.get('reviewer_id'))
            db.execute("UPDATE cp_revisions SET status='submitted',reviewer_id=? WHERE id=?",(reviewer,rev['id']))
            store.notify(db,user,obj,[reviewer],'Knowledge contribution awaiting review',rev['title'])
        elif action in {'approve','reject'}:
            if rev['status']!='submitted' or rev['reviewer_id']!=user['id']:raise HTTPException(403,'Only the assigned reviewer can decide this submission.')
            store.review_user(db,obj['project_id'],obj['author_id'],user['id'])
            if not comment:raise HTTPException(400,'Record the review checks or reason for rejection.')
            caps=store.capabilities(payload.get('capabilities',[])) if action=='approve' else []
            db.execute('UPDATE cp_revisions SET status=?,reviewed_at=?,reviewed_by=?,review_comment=?,verified_capabilities=? WHERE id=?',('approved' if action=='approve' else 'rejected',now,user['id'],comment,encode(caps),rev['id']))
            if action=='approve':db.execute('UPDATE cp_articles SET approved_revision=?,updated_at=? WHERE id=?',(rev['id'],now,key))
            store.notify(db,user,obj,[obj['author_id']],'Knowledge contribution '+('approved' if action=='approve' else 'returned'),comment)
        elif action=='publish':
            if rev['status']!='approved' or obj['approved_revision']!=rev['id'] or rev['reviewer_id']!=user['id']:raise HTTPException(403,'The assigned reviewer can publish the exact approved revision.')
            store.review_user(db,obj['project_id'],obj['author_id'],user['id'])
            db.execute("UPDATE cp_revisions SET status='published',published_at=?,published_by=? WHERE id=?",(now,user['id'],rev['id']))
            db.execute('UPDATE cp_articles SET published_revision=?,updated_at=? WHERE id=?',(rev['id'],now,key))
            db.execute('INSERT OR REPLACE INTO cp_search VALUES(?,?,?,?,?,?)',(key,rev['id'],rev['title'],rev['category'],' '.join(rev['keywords']),rev['body']))
            fts=db.execute("SELECT value FROM pc_state WHERE key='fts'").fetchone()
            if fts and fts[0]=='1':
                db.execute('DELETE FROM cp_search_fts WHERE article_id=?',(key,))
                db.execute('INSERT INTO cp_search_fts(article_id,revision_id,title,keywords,body) VALUES(?,?,?,?,?)',(key,rev['id'],rev['title'],' '.join(rev['keywords']),rev['body']))
            store.notify(db,user,obj,[obj['author_id']],'Knowledge article published',rev['title'])
        else:raise HTTPException(400,'Choose submit, approve, reject or publish.')
        store.action(db,user,'article',key,rev['id'],action,{'comment':comment})
    return detail(user,key)


def search(user,query='',category='',project_id='',author_id=None,page=1,page_size=20):
    store.initialize();store.personal(user);query=text(query,500);page=max(1,min(10000,page));page_size=max(1,min(50,page_size))
    if category and category not in store.CATEGORIES:raise HTTPException(400,'Choose a library category.')
    clauses=['a.published_revision=s.revision_id'];params=[]
    if category:clauses.append('s.category=?');params.append(category)
    if project_id:clauses.append('a.project_id=?');params.append(project_id)
    if author_id is not None:clauses.append('a.author_id=?');params.append(author_id)
    with hub.db() as db:
        stop={'how','did','does','the','and','for','what','when','where','with','this','that','our','are','can','was','you','from','have','were','which'}
        tokens=[token for token in re.findall(r'[\w+#.-]+',query,re.UNICODE) if len(token)>1 and token.casefold() not in stop][:12];fts=db.execute("SELECT value FROM pc_state WHERE key='fts'").fetchone();join='';order='r.published_at DESC'
        if tokens and fts and fts[0]=='1':
            phrase=' OR '.join('"'+token.replace('"','""')+'"' for token in tokens)
            join=' JOIN cp_search_fts ON cp_search_fts.article_id=s.article_id AND cp_search_fts.revision_id=s.revision_id'
            clauses.append('cp_search_fts MATCH ?');params.append(phrase);order='bm25(cp_search_fts),r.published_at DESC'
        elif tokens:
            clauses.append('('+' OR '.join('(s.title LIKE ? ESCAPE \'\\\' OR s.keywords LIKE ? ESCAPE \'\\\' OR s.body LIKE ? ESCAPE \'\\\')' for _ in tokens)+')')
            for token in tokens:
                value='%'+token.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';params.extend([value]*3)
        source=' FROM cp_search s JOIN cp_articles a ON a.id=s.article_id JOIN cp_revisions r ON r.id=s.revision_id'+join+' WHERE '+' AND '.join(clauses)
        total=db.execute('SELECT COUNT(*)'+source,params).fetchone()[0]
        values=[{**dict(row),'keywords':json.loads(row['keywords'])} for row in db.execute('SELECT s.article_id AS id,s.revision_id,s.title,s.category,substr(s.body,1,700) AS excerpt,a.author_id,a.project_id,a.task_id,r.keywords,r.number,r.published_at,r.reviewed_by'+source+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*params,page_size,(page-1)*page_size))]
        return {'items':values,'total':total,'page':page,'page_size':page_size}


def workspace(user):
    store.initialize();store.personal(user)
    with hub.db() as db:
        articles=[];queue=[];manual_queue=[]
        for row in db.execute('SELECT a.*,r.title,r.category,r.number,r.status,r.reviewer_id,r.review_comment FROM cp_articles a JOIN cp_revisions r ON r.id=a.current_revision ORDER BY a.updated_at DESC'):
            if row['author_id']==user['id']:articles.append(dict(row))
            if row['status'] in {'submitted','approved'} and (row['reviewer_id']==user['id'] or user['role']=='admin'):queue.append(dict(row))
        for row in db.execute('SELECT m.*,r.content,r.status,r.reviewer_id,r.number FROM pc_manual m JOIN pc_manual_revisions r ON r.id=m.current_revision WHERE r.status=\'submitted\' ORDER BY m.updated_at DESC'):
            if row['reviewer_id']==user['id'] or user['role']=='admin':manual_queue.append({**dict(row),'content':json.loads(row['content'])})
        return {'articles':articles,'article_reviews':queue,'evidence_reviews':manual_queue,'questions':{key:[{'id':q[0],'question':q[1],'options':q[2]} for q in values] for key,values in QUESTIONS.items()}}


def assistant(user,payload):
    question=text(payload.get('question',''),3000,True)
    found=search(user,question,project_id=payload.get('project_id') or '',page_size=5)['items']
    if not found:return {'answer':'No published, reviewed article matched this question. Try another keyword or submit the unresolved problem as a contribution.','sources':[],'mode':'library_search'}
    sources=[]
    with hub.db() as db:
        for row in found:
            rev=store.revision(db,'article',row['revision_id'],row['id'])
            sources.append({'id':row['id'],'revision_id':row['revision_id'],'title':row['title'],'text':rev['body'][:9000],'excerpt_only':len(rev['body'])>9000,'url':'/?workhubArticle='+row['id']+'&workhubArticleRevision='+row['revision_id']})
    answer='Relevant reviewed knowledge:\n\n'+'\n\n'.join('['+str(i+1)+'] '+source['title']+'\n'+source['text'][:1200] for i,source in enumerate(sources))
    mode='source_excerpts';notice='Showing source excerpts. Read the article and its applicability limits before reusing a method.'
    if payload.get('use_local_ai') is True:
        from backend.core.workhub_intelligence.local_ai import llm_json,ServiceUnavailable
        try:
            value=llm_json('Answer the troubleshooting question using only the published reviewed articles. Return {"answer":"...","source_ids":["article-id"]}. Preserve limits, technical values and uncertainty; do not invent a machine diagnosis. Sources marked excerpt_only are incomplete: do not infer missing conditions or claim the article omits details. Cite article IDs in the answer.',{'question':question,'sources':sources})
            refs=value.get('source_ids')
            if not isinstance(refs,list) or not refs or any(key not in {s['id'] for s in sources} for key in refs):raise ValueError('The local answer omitted valid article citations.')
            answer=text(value.get('answer',''),16000,True);sources=[s for s in sources if s['id'] in refs];mode='local_ai';notice='Local explanation based on the linked published revisions. Engineering applicability still needs review.'
        except (ServiceUnavailable,ValueError,HTTPException):notice='The local explanation was unavailable or lacked valid citations. Showing the reviewed source excerpts instead.'
    if any(source.get('excerpt_only') for source in sources):notice+=' Some sources are excerpts; open the complete article revision for the full method and limits.'
    return {'answer':answer,'sources':[{k:v for k,v in source.items() if k!='text'} for source in sources],'mode':mode,'notice':notice}


def polish(user,key,payload):
    value=detail(user,key);store.author(user,value['article'])
    if payload.get('version')!=value['article']['current_revision']:raise HTTPException(409,'This article changed. Refresh before drafting.')
    rev=value['revision']
    if len(rev['body'])+sum(len(value) for value in rev['answers'].values())>40000:raise HTTPException(413,'This contribution exceeds the local drafting context. Edit it manually or split it into smaller articles.')
    from backend.core.workhub_intelligence.local_ai import llm_json,ServiceUnavailable
    try:result=llm_json('Prepare a clear engineering knowledge article from the supplied author answers. Return {"body":"Markdown article"}. Preserve every technical value, caveat and uncertainty. Do not introduce diagnoses, results, names or requirements. Include the limitations and verification status.',{'title':rev['title'],'category':store.CATEGORIES[rev['category']],'author_answers':rev['answers'],'current_draft':rev['body']})
    except ServiceUnavailable as error:raise HTTPException(503,str(error))
    return {'body':text(result.get('body',''),100000,True),'notice':'Proposed wording only. Review it against your answers before saving a new revision.'}
