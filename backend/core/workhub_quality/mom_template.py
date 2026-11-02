"""MOM report sections shared by the controlled HTML and fallback PDF renderers."""
import json
def blocks(content):
    def section(key,title,columns=(),rows=(),text=''):
        return {'key':key,'title':title,'text':text,'columns':list(columns),'rows':list(rows),'svg':''}
    participants=content.get('participant_details') or [{'name':name} for name in content.get('participants',[])]
    topics=content.get('discussion_summary',[]);decisions=content.get('decisions',[]);next_meeting=content.get('next_meeting',{})
    result=[
      section('summary','Meeting Details',['Field','Detail'],[
        ['Meeting title',content.get('meeting_subject') or 'Not recorded'],['Date',content.get('meeting_date') or 'Not recorded'],
        ['Time',' – '.join(v for v in (content.get('meeting_start_time'),content.get('meeting_end_time')) if v) or 'Not recorded'],
        ['Mode',content.get('meeting_mode') or 'Not recorded'],['Location / Platform',content.get('location') or 'Not recorded'],
        ['Meeting Type',', '.join(content.get('meeting_types',[])) or 'Not confirmed']]),
      section('scope','Meeting Objective',text=content.get('meeting_objective') or content.get('purpose') or 'Not recorded'),
      section('purpose','Agenda',text=content.get('agenda') or 'Not recorded'),
      section('sections','Participants',['#','Name','Role / Organization','Attendance'],[
        [i+1,p.get('name',''),' / '.join(v for v in (p.get('role'),p.get('organization')) if v),p.get('attendance') or 'Not confirmed'] for i,p in enumerate(participants)]),
      section('sections','Discussion Summary',['No.','Discussion Points','Key Discussion / Outcome'],[
        [i+1,r.get('topic',''),'\n'.join(v for v in (r.get('text'),r.get('decision') or (decisions[i].get('text') if i<len(decisions) else '')) if v)] for i,r in enumerate(topics)] or [[i+1,'Decision',r.get('text','')] for i,r in enumerate(decisions)]),
      section('sections','Action Items',['#','Action Item','Owner','Target Date','Status'],[
        [r.get('id') or 'A'+str(i+1),r.get('text',''),r.get('responsible') or 'Unassigned',r.get('target_date') or 'Not recorded',r.get('status') or 'Open'] for i,r in enumerate(content.get('actions',[]))]),
      section('sections','Next Meeting',['Date','Time','Mode'],[[next_meeting.get('date') or 'Not recorded',next_meeting.get('time') or 'Not recorded',next_meeting.get('mode') or 'Not recorded']],content.get('follow_up') or '\n'.join(r.get('text','') for r in content.get('next_meeting_items',[])))]
    if content.get('clarifications'):result.append(section('sections','Open Clarifications',['#','Clarification'],[[i+1,r.get('question') or r.get('text','')] for i,r in enumerate(content['clarifications'])]))
    if content.get('sources'):result.append(section('details','Source References',['Reference','Location','Source excerpt'],[
        [r.get('id',''),json.dumps({k:v for k,v in r.items() if k!='text'},ensure_ascii=False),r.get('text','')] for r in content['sources']]))
    return result
