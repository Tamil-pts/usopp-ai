import {useEffect,useRef} from 'react';
import * as echarts from 'echarts/core';
import {BarChart,LineChart,RadarChart,HeatmapChart,PieChart,GaugeChart} from 'echarts/charts';
import {GridComponent,TooltipComponent,LegendComponent,RadarComponent,VisualMapComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
echarts.use([BarChart,LineChart,RadarChart,HeatmapChart,PieChart,GaugeChart,GridComponent,TooltipComponent,LegendComponent,RadarComponent,VisualMapComponent,CanvasRenderer]);

export default function Charts({option,label,onSelect,height=310}:{option:any;label:string;onSelect?:(value:any)=>void;height?:number}){
 const node=useRef<HTMLDivElement>(null),select=useRef(onSelect);select.current=onSelect;
 useEffect(()=>{
  if(!node.current)return;
  const chart=echarts.init(node.current);const apply=()=>{if(!node.current)return;const style=getComputedStyle(node.current),color=style.getPropertyValue('--text').trim()||'#243c48';
   const axis=(value:any)=>value?{...value,axisLabel:{...value.axisLabel,color},axisLine:{...value.axisLine,lineStyle:{color:style.getPropertyValue('--line2').trim()}}}:value;
   chart.setOption({...option,textStyle:{fontFamily:'inherit',color},xAxis:axis(option.xAxis),yAxis:axis(option.yAxis),legend:option.legend?{...option.legend,textStyle:{color}}:undefined,visualMap:option.visualMap?{...option.visualMap,textStyle:{color}}:undefined,radar:option.radar?{...option.radar,axisName:{color}}:undefined,tooltip:{...option.tooltip,renderMode:'richText'},backgroundColor:'transparent'},true);};
  apply();chart.on('click',value=>select.current?.(value));const resize=new ResizeObserver(()=>chart.resize());resize.observe(node.current);
  const theme=new MutationObserver(apply);theme.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','class','style']});
  return()=>{resize.disconnect();theme.disconnect();chart.dispose();};
 },[option]);
 return <div className="px-chart" ref={node} style={{height}} role="img" aria-label={label}/>;
}
