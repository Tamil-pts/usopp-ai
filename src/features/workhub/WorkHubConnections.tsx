import {useEffect,useState} from 'react';
import {ExternalLink,Mail,MessageSquare,Settings2,Unplug} from 'lucide-react';
import {useAccount} from '../account/AuthProvider';
import {hub,HUB,type HubRow} from './projectApi';
import './projects.css';

export function WorkHubConnections(){
  const {user}=useAccount();
  const [settings,setSettings]=useState<HubRow|null>(null),[draft,setDraft]=useState<HubRow>({}),[company,setCompany]=useState<HubRow>({});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const load=async()=>{
    const value=await hub('/connections');setSettings(value);
    setDraft({...value,teams_url:'',shared_teams_chat_url:value.configuration.teams_chat_url||'',public_url:value.configuration.public_url||''});
    setCompany({...value.configuration,client_secret:''});
  };
  useEffect(()=>{if(!user.isDemo)void load().catch(error=>setError(error.message));},[user.id]);
  const save=async(companySettings=false,removeWorkflow=false)=>{
    setBusy(true);setError('');setMessage('');
    try{
      const payload=companySettings?company:{contact_email:draft.contact_email,teams_chat_url:draft.teams_chat_url,teams_mode:removeWorkflow?'chat':draft.teams_mode,
        teams_url:removeWorkflow?'':draft.teams_url,teams_enabled:removeWorkflow?false:draft.teams_enabled,email_enabled:draft.email_enabled,disconnect_teams:removeWorkflow,
        ...(user.role==='admin'?{shared_teams_chat_url:draft.shared_teams_chat_url,public_url:draft.public_url}:{})};
      await hub(companySettings?'/connections/company':'/connections',payload,'PUT');await load();
      window.dispatchEvent(new Event('workhub-updated'));
      setMessage(companySettings?'Microsoft application settings saved.':removeWorkflow?'Automatic Teams workflow removed. Group chat sharing is selected.':'Notification and sharing settings saved.');
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  };
  const disconnect=async()=>{setBusy(true);setError('');try{await hub('/connections/microsoft',undefined,'DELETE');await load();setMessage('Microsoft account disconnected.');}catch(error){setError((error as Error).message);}finally{setBusy(false);}};
  if(user.isDemo)return null;
  const candidate=draft.teams_chat_url||draft.shared_teams_chat_url||'';
  let chatLink='';try{const link=new URL(candidate);if(link.protocol==='https:'&&['teams.microsoft.com','teams.cloud.microsoft','teams.live.com'].includes(link.hostname)&&!link.username&&!link.password&&(!link.port||link.port==='443'))chatLink=candidate;}catch{}
  return <section id="workhub-notifications" className="card wh-connections">
    <div className="wh-section-heading"><div><span className="workHubEyebrow">WORKHUB SETTINGS</span><h2>Notifications and Teams sharing</h2></div><Settings2 size={22}/></div>
    <p>Assignments and approvals appear in the notification bell. Use your existing Teams group chat to share a work update without setting up a Microsoft application.</p>
    {error&&<p role="alert" className="wh-error">{error}</p>}{message&&<p role="status" className="wh-success">{message}</p>}
    {!settings?<p>Loading settings...</p>:<>
      <div className="wh-connection-box">
        <h3><MessageSquare size={18}/> Teams group chat</h3>
        <p>In your Teams group, use a message's More options &gt; Copy link. Paste the chat or message link here.</p>
        {user.role==='admin'?<>
          <label>Shared group chat link<input className="textInput" type="url" placeholder="https://teams.microsoft.com/l/chat/..." value={draft.shared_teams_chat_url||''} onChange={event=>setDraft({...draft,shared_teams_chat_url:event.target.value})}/></label>
          <small>This is the default group for all WorkHub users. Existing group membership is required to view the conversation.</small>
        </>:settings.configuration.teams_chat_url?<p>A shared WorkHub group chat is configured by Admin.</p>:<p>Paste your own group link below, or ask Admin to save one shared group for the team.</p>}
        <details><summary>My own group chat (optional)</summary><label>Personal group chat link<input className="textInput" type="url" placeholder="Leave blank to use the shared group" value={draft.teams_chat_url||''} onChange={event=>setDraft({...draft,teams_chat_url:event.target.value})}/></label></details>
        <label>Teams notification method<select className="textInput" value={draft.teams_mode||'chat'} onChange={event=>setDraft({...draft,teams_mode:event.target.value})}><option value="chat">Group chat link - copy and send manually</option><option value="workflow">Automatic workflow - requires an approved connection</option></select></label>
        <div className="wh-manual-share-note"><b>Copy &amp; open Teams</b><p>On a project, task or notification, select Share in Teams. Review the prepared message, copy it, open this group, then paste and send in Teams. Approval decisions are recorded in WorkHub.</p></div>
        {chatLink&&<a className="btn" href={chatLink} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/>Open group chat</a>}
      </div>
      {user.role==='admin'&&<details className="wh-company"><summary>WorkHub address for shared review links (optional)</summary><p>Enter the address colleagues use to open WorkHub, such as an office server or LAN address. A localhost address points to each person's own computer.</p><label>WorkHub address<input className="textInput" type="url" placeholder="http://192.168.1.10:8200" value={draft.public_url||''} onChange={event=>setDraft({...draft,public_url:event.target.value})}/></label><small>Changing this address disconnects existing Microsoft mail authorizations. Group chat sharing does not require mail authorization.</small></details>}
      <details className="wh-company"><summary>Automatic email and Teams connections (optional, when approved)</summary>
        <p>These connections can be configured later when your organization permits them. Group chat sharing works independently.</p>
        <div className="wh-two-columns"><div className="wh-connection-box">
          <h3><Mail size={18}/> My company email</h3>
          <label>Contact email<input className="textInput" type="email" value={draft.contact_email||''} onChange={event=>setDraft({...draft,contact_email:event.target.value})}/></label>
          <p>{settings.mail_connected?<>Connected: <b>{settings.mail_address}</b></>:'Connect your own Microsoft 365 / Outlook mailbox when company authorization is available.'}</p>
          {settings.mail_connected?<button className="btn" disabled={busy} onClick={()=>void disconnect()}><Unplug size={15}/>Disconnect my email</button>:<a className={'btn '+(!settings.configuration.microsoftReady?'disabled':'primary')} aria-disabled={!settings.configuration.microsoftReady} href={settings.configuration.microsoftReady?HUB+'/connections/microsoft/start':undefined}>Connect my Microsoft account</a>}
          {!settings.configuration.microsoftReady&&<small>Company Microsoft application setup is required for automatic email.</small>}
          <label className="wh-check"><input type="checkbox" disabled={!settings.mail_connected} checked={!!draft.email_enabled} onChange={event=>setDraft({...draft,email_enabled:event.target.checked})}/>Send workflow notifications from my connected mailbox when I act on work.</label>
        </div><div className="wh-connection-box">
          <h3><MessageSquare size={18}/> Automatic Teams workflow</h3>
          <p>{settings.teams_connected?'A workflow destination is saved.':'When permitted, create a workflow that receives a webhook request and posts its Adaptive Card to Teams.'}</p>
          <label>Workflow URL<input className="textInput" type="password" autoComplete="new-password" value={draft.teams_url||''} placeholder={settings.teams_connected?'Leave blank to keep the saved workflow URL':'Microsoft workflow URL (not a chat link)'} onChange={event=>setDraft({...draft,teams_url:event.target.value})}/></label>
          <label className="wh-check"><input type="checkbox" disabled={draft.teams_mode!=='workflow'} checked={!!draft.teams_enabled} onChange={event=>setDraft({...draft,teams_enabled:event.target.checked})}/>Enable automatic Teams delivery</label>
          <small>Choose Automatic workflow above to enable this connection. The supported workflow uses a private signed URL with an Anyone trigger.</small>
          {settings.teams_connected&&<button className="btn" disabled={busy} onClick={()=>void save(false,true)}>Remove saved workflow</button>}
        </div></div>
      </details>
      <button className="btn primary" disabled={busy} onClick={()=>void save()}>{busy?'Saving...':'Save notification settings'}</button>
      {user.role==='admin'&&<details className="wh-company"><summary>Microsoft application setup (Admin, when approved)</summary>
        <p>For future automatic email, register a Web application with delegated User.Read and Mail.Send permissions. Users authorize their own mailboxes. A company callback address needs HTTPS.</p>
        <div className="wh-form-grid"><label>Microsoft tenant ID / domain<input className="textInput" value={company.tenant_id||''} onChange={event=>setCompany({...company,tenant_id:event.target.value})}/></label><label>Application client ID<input className="textInput" value={company.client_id||''} onChange={event=>setCompany({...company,client_id:event.target.value})}/></label><label>Client secret<input className="textInput" type="password" autoComplete="new-password" value={company.client_secret||''} placeholder={company.hasClientSecret?'Leave blank to keep the saved secret':''} onChange={event=>setCompany({...company,client_secret:event.target.value})}/></label><label>HTTPS application address<input className="textInput" value={company.public_url||''} onChange={event=>setCompany({...company,public_url:event.target.value})}/></label></div>
        <p className="wh-mono">{company.public_url||'https://usop.company.com'}/api/workhub/connections/microsoft/callback</p>
        <button className="btn" disabled={busy} onClick={()=>void save(true)}>Save Microsoft application settings</button>
      </details>}
    </>}
  </section>;
}
