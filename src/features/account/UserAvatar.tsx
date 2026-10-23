import type {AccountUser} from './AuthProvider';

export function UserAvatar({user,size=36}:{user:AccountUser;size?:number}){
 return <span className="userAvatar" style={{width:size,height:size,fontSize:Math.max(12,size/3)}} role="img" aria-label={`${user.username}'s profile photo`}>
  <span aria-hidden="true">{user.username.slice(0,2).toUpperCase()}</span>
  {user.avatarUrl&&<img key={user.avatarUrl} src={user.avatarUrl} alt="" onError={event=>{event.currentTarget.hidden=true}}/>}
 </span>;
}
