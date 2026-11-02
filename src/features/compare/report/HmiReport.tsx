import {createRoot} from 'react-dom/client';
import {Component,useEffect,type ReactNode} from 'react';
import {HmiScreenPreview} from '../HmiScreenPreview';
import './hmi-report.css';

class ReportBoundary extends Component<{element:HTMLElement;children:ReactNode},{failed:boolean}> {
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true}}
 componentDidCatch(){this.props.element.dataset.mounted='failed'}
 render(){return this.state.failed?null:this.props.children}
}
function Screen({element,data}:{element:HTMLElement;data:any}) {
 useEffect(()=>{element.dataset.mounted='true'},[element]);
 return <HmiScreenPreview data={data.screen} baseLabel={data.baseLabel} newLabel={data.newLabel} skipLayout={data.skipLayout}/>;
}

// The report carries its own data, rendering code and images. It never contacts
// the app, and uses the same control pairing and property inspector as MatchView.
function mount(element:HTMLElement) {
 if(element.dataset.mounted)return;
 try {
  const encoded=element.querySelector<HTMLScriptElement>('script[data-hmi-data]');
  const target=element.querySelector<HTMLElement>('[data-hmi-mount]');
  if(!encoded||!target)return;
  const data=JSON.parse(encoded.textContent||'{}');
  element.dataset.mounted='loading';
  createRoot(target).render(<ReportBoundary element={element}><Screen element={element} data={data}/></ReportBoundary>);
 }catch {
  // The complete static comparison remains available if the interactive view fails.
  element.dataset.mounted='failed';
 }
}
const reports=document.querySelectorAll<HTMLElement>('[data-hmi-report]');
if('IntersectionObserver' in window){
 const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){mount(entry.target as HTMLElement);observer.unobserve(entry.target)}}),{rootMargin:'600px'});
 reports.forEach(element=>observer.observe(element));
}else reports.forEach(mount);
