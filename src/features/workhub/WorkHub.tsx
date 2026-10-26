import type {ReactNode} from 'react';
import {WorkHubProjects} from './WorkHubProjects';
import './workhub.css';

type WorkHubProps={active:boolean;renderRecentWork:(active:boolean)=>ReactNode};

export function WorkHub({active,renderRecentWork}:WorkHubProps){
  return <WorkHubProjects active={active} renderRecentWork={renderRecentWork}/>;
}
