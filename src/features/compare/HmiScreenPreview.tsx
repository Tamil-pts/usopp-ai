import {userStorage} from '../../shared/userStorage';
import React, {useState} from 'react';
import {useLinkedScroll} from './useLinkedScroll';
import {ResizeHandle} from './ResizeHandle';
import {HmiPropertyComparison} from './HmiPropertyComparison';
import {bitmapLabel,selectBitmap,previewBitmapProperties,type BitmapStates,type BitmapAssets} from './hmiBitmaps';
import {visiblePreviewLayers,controlsAtPoint,controlSelectionGroups} from './hmiControlSelection';

type Control = {
  id:string; name:string; class:string; class_id:string; status:string;
  left:number; top:number; width:number; height:number;
  properties:Record<string,string>; effective_properties:Record<string,string>;
  texts:Record<string,string>; datapoint:string; fonts?:Record<string,Record<string,string>>;
  bitmaps?:BitmapStates;
};
type Layer = {id:string; name:string; left:number; top:number; hidden:boolean; controls:Control[]; properties:Record<string,string>};
type Layout = {name:string; width:number; height:number; palette:Record<string,string>; properties:Record<string,string>; layers:Layer[]; warnings:string[];bitmaps?:BitmapStates;bitmap_assets?:BitmapAssets;touchpad_levels?:number};
const colors:Record<string,string> = {modified:'#d38a0a', added:'#19854b', removed:'#d13d49', unchanged:'#13899a'};
const symbol:Record<string,string> = {modified:'\u2192', added:'+', removed:'\u2212', unchanged:'='};

function paletteColor(layout:Layout, value:string|undefined, fallback:string) {
  const color = value ? layout.palette[value] || value : '';
  return /^#[\da-f]{3}([\da-f]{3})?$/i.test(color) ? color : fallback;
}

function ControlBox({control:c, layout, language, bitmapState, selected, names, fontScale, onSelect}:{control:Control; layout:Layout; language:string;bitmapState:'released'|'pressed'; selected:boolean; names:boolean; fontScale:number; onSelect:(event?:React.MouseEvent<SVGGElement>)=>void}) {
  const p=c.effective_properties;
  const text=c.texts[language] ?? c.texts.en ?? Object.values(c.texts)[0];
  const bound=['Numeric','String','TouchPadEdit'].includes(c.class);
  const binding=c.datapoint && !['None','<None>'].includes(c.datapoint) ? c.datapoint : '';
  const bitmap=selectBitmap(c.bitmaps,bitmapState,0,language);
  const asset=bitmap?.asset_id?layout.bitmap_assets?.[bitmap.asset_id]:undefined;
  const label=bound ? binding || p.SimulationValue || '' : text ?? (bitmap&&!asset?bitmapLabel(bitmap):'');
  const font=c.fonts?.[language]??c.fonts?.[language.split('-')[0]]??c.fonts?.en??{};
  const sourceSize=Number(font.Size);
  const defaultSize=layout.width<=320?9:12;
  const configuredSize=Number.isFinite(sourceSize)&&sourceSize>0?sourceSize*4/3:defaultSize;
  const multiline=!bound&&p.Multiline!=='Disable';
  // Keep long PLC identifiers inside their box. The inspector retains the full value.
  const fitSize=bound&&binding?Math.max(4,(c.width-4)/Math.max(1,binding.length*.55)):configuredSize;
  const fontSize=Math.min(configuredSize,fitSize)*fontScale/100;
  const background=['HotSpot','TouchPadGrid'].includes(c.class)||p.FillStyle==='Transparent'||(!p.BackColor&&c.class==='Text') ? 'transparent' : paletteColor(layout,p.BackColor,'#edf3f7');
  const foreground=paletteColor(layout,p.ForeColor,'#122c40');
  const changed=c.status!=='unchanged';
  const border=selected?'#2563eb':changed?colors[c.status]:p.Border&&!p.Border.includes('None')?'#98a2b3':'transparent';
  const center=p.AlignmentHorizontal==='Center'||(!p.AlignmentHorizontal&&['Numeric','Button','TouchPadEdit'].includes(c.class));
  const align=center?'center':p.AlignmentHorizontal==='Right'?'right':'left';
  return <g className="hmiPreviewControl" role="button" tabIndex={0} aria-label={`${c.name}: ${label}. ${c.status}`} onClick={e=>{e.stopPropagation();onSelect(e)}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect()}}}>
    <title>{`${c.name} (${c.class})\n${label}\nLeft ${c.left}, Top ${c.top}, Width ${c.width}, Height ${c.height}\nClick for all properties`}</title>
    <rect x={c.left} y={c.top} width={c.width} height={c.height} fill={background} stroke={border} strokeWidth={selected?3:changed?2:1}/>
    {asset?.data_uri&&<image className="hmiPreviewBitmap" href={asset.data_uri} x={c.left} y={c.top} width={c.width} height={c.height} preserveAspectRatio="none" pointerEvents="none"><title>{bitmapLabel(bitmap)}</title></image>}
    {asset&&(selected||changed)&&<rect x={c.left} y={c.top} width={c.width} height={c.height} fill="none" stroke={border} strokeWidth={selected?3:2} pointerEvents="none"/>}
    <foreignObject x={c.left} y={c.top} width={c.width} height={c.height} pointerEvents="none">
      <div className="hmiPreviewControlLabel" style={{color:foreground, textAlign:align, alignItems:align==='center'?'center':align==='right'?'flex-end':'flex-start', justifyContent:p.AlignmentVertical==='Top'?'flex-start':p.AlignmentVertical==='Bottom'?'flex-end':'center',fontSize,fontFamily:font.Family||'Arial, sans-serif',fontWeight:font.Bold==='True'?700:400,fontStyle:font.Italic==='True'?'italic':'normal',whiteSpace:multiline?'pre-wrap':'pre',overflowWrap:multiline?'break-word':'normal'}}>
        {names&&<small>{c.name}</small>}<span>{label}</span>
      </div>
    </foreignObject>
    {changed&&<g pointerEvents="none"><circle cx={c.left+6} cy={c.top+6} r={7} fill={colors[c.status]}/><text x={c.left+6} y={c.top+10} textAnchor="middle" fill="white" fontSize={12}>{symbol[c.status]}</text></g>}
  </g>;
}

export function HmiScreenPreview({data,baseLabel,newLabel,skipLayout=false}:{data:any;baseLabel:string;newLabel:string;skipLayout?:boolean}) {
  const screenScroll=useLinkedScroll();
  const previewRef=React.useRef<HTMLDivElement>(null);
  const toolbarRef=React.useRef<HTMLDivElement>(null);
  const inspectorRef=React.useRef<HTMLDivElement>(null);
  const showProperties=()=>{
    const preview=previewRef.current,inspector=inspectorRef.current;
    if(preview&&inspector)preview.scrollTo({top:preview.scrollTop+inspector.getBoundingClientRect().top-preview.getBoundingClientRect().top-(toolbarRef.current?.offsetHeight||0),behavior:'smooth'});
  };
  const [selected,setSelected]=useState<string|null>(null);
  const [overlap,setOverlap]=useState<{side:number;ids:string[]}|null>(null);
  const [canvasHeight,setCanvasHeight]=useState(620);
  const [language,setLanguage]=useState('en');
  const [layerFilter,setLayerFilter]=useState('visible');
  const [zoom,setZoom]=useState('fit');
  const [names,setNames]=useState(false);
  const [bitmapState,setBitmapState]=useState<'released'|'pressed'>('released');
  const [bitmapLevel,setBitmapLevel]=useState(0);
  const [fontScale,setFontScale]=useState(()=>{try{const n=Number(userStorage.getItem('usopp_hmi_font_scale'));return n>=25&&n<=150?n:100}catch{return 100}});
  const changeFontScale=(value:number)=>{setFontScale(value);try{userStorage.setItem('usopp_hmi_font_scale',String(value))}catch{/* Preview still works when browser storage is unavailable. */}};
  const layouts:[Layout|undefined,Layout|undefined]=[data.layouts?.base?.layers?data.layouts.base:undefined,data.layouts?.new?.layers?data.layouts.new:undefined];
  const layers=Array.from(new Map(layouts.flatMap(l=>l?.layers||[]).map(l=>[l.id,l])).values());
  const selectionGroups=controlSelectionGroups(layouts);
  const chooseControl=(id:string|null,inspect=false)=>{
    setSelected(id);setOverlap(null);
    if(id){
      const containing=layouts.flatMap(layout=>layout?.layers||[]).filter(layer=>layer.controls.some(control=>control.id===id));
      if(!containing.some(layer=>visiblePreviewLayers([layer],layerFilter).length))setLayerFilter(containing[0]?.id||'all');
    }
    if(inspect)showProperties();
  };
  const pickControl=(layout:Layout,layer:Layer,control:Control,side:number,event?:React.MouseEvent<SVGGElement>)=>{
    let x=layer.left+control.left+control.width/2,y=layer.top+control.top+control.height/2;
    const svg=event?.currentTarget.ownerSVGElement,matrix=svg?.getScreenCTM();
    if(event&&svg&&matrix){const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const source=point.matrixTransform(matrix.inverse());x=source.x;y=source.y}
    const hits=controlsAtPoint(layout.layers,layerFilter,x,y);
    setSelected(control.id);
    setOverlap(hits.length>1?{side,ids:hits.map(hit=>hit.control.id)}:null);
  };
  const languages=Array.from(new Set(['en',...layouts.flatMap(l=>l?.layers.flatMap(layer=>layer.controls.flatMap(c=>Object.keys(c.texts)))||[]),...layouts.flatMap(l=>Object.values(l?.bitmaps||{}).flatMap(state=>state?.variants.map(variant=>variant.language)||[])).filter(lang=>lang!=='neutral')])).sort();
  const maxBitmapLevels=Math.min(64,Math.max(1,...layouts.map(layout=>layout?.touchpad_levels||1)));
  const hasBitmaps=layouts.some(layout=>Object.keys(layout?.bitmaps||{}).length||layout?.layers.some(layer=>layer.controls.some(control=>Object.keys(control.bitmaps||{}).length)));
  const getControl=(l:Layout|undefined)=>l?.layers.flatMap(layer=>layer.controls).find(c=>c.id===selected);
  const controls=layouts.map(getControl);
  const properties=layouts.map((l,i)=>selected?(controls[i]?{Name:controls[i]!.name,ClassId:controls[i]!.class_id,...previewBitmapProperties(controls[i]!.effective_properties,controls[i]!.bitmaps,0,language),...Object.fromEntries(Object.entries(controls[i]!.texts).map(([lang,value])=>[`Text (${lang})`,value]))}:{}):previewBitmapProperties(l?.properties||{},l?.bitmaps,bitmapLevel,language));
  return <div className="hmiPreview" ref={previewRef}>
    <div className="hmiPreviewToolbar" ref={toolbarRef}>
      <div className="hmiFontButtons" role="group" aria-label="Preview font size">
        <button title="Reduce font size" aria-label="Reduce font size" disabled={fontScale<=25} onClick={()=>changeFontScale(Math.max(25,fontScale-5))}>A− Smaller</button>
        <output aria-live="polite">{fontScale}%</output>
        <button title="Increase font size" aria-label="Increase font size" disabled={fontScale>=150} onClick={()=>changeFontScale(Math.min(150,fontScale+5))}>A+ Larger</button>
      </div>
      <label>Language <select value={language} onChange={e=>setLanguage(e.target.value)}>{languages.map(lang=><option key={lang}>{lang}</option>)}</select></label>
      <label>Layers <select aria-label="Layers" value={layerFilter} onChange={e=>{setLayerFilter(e.target.value);setOverlap(null)}}><option value="visible">Normally visible layers</option><option value="all">All layers (including hidden)</option>{layers.map(l=><option key={l.id} value={l.id}>{l.name}{l.hidden?' (hidden)':''}</option>)}</select></label>
      <label>Control <select aria-label="Select HMI control" className="hmiControlSelect" value={selected||''} onChange={event=>chooseControl(event.target.value||null)}><option value="">Screen properties</option>{selectionGroups.map(group=><optgroup key={group.id} label={`${group.name}${group.hidden?' (hidden)':''}`}>{group.controls.map(({control,present})=><option key={control.id} value={control.id}>{control.name} · {control.class}{!present[0]?' (Developed only)':!present[1]?' (Base only)':''}</option>)}</optgroup>)}</select></label>
      <label>Zoom <select aria-label="Zoom" value={zoom} onChange={e=>setZoom(e.target.value)}><option value="fit">Fit</option><option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option></select></label>
      <label>Font size <input aria-label="HMI font size" type="range" min="25" max="150" step="5" value={fontScale} onChange={e=>changeFontScale(Number(e.target.value))}/></label>
      <button onClick={()=>changeFontScale(100)}>Reset font</button>
      <label><input type="checkbox" checked={names} onChange={e=>setNames(e.target.checked)}/> Control names</label>
      {hasBitmaps&&<label>Bitmap state <select aria-label="Preview bitmap state" value={bitmapState} onChange={event=>setBitmapState(event.target.value as typeof bitmapState)}><option value="released">Released</option><option value="pressed">Pressed</option></select></label>}
      {maxBitmapLevels>1&&<label>Touchpad level <select aria-label="Preview touchpad level" value={bitmapLevel} onChange={event=>setBitmapLevel(Number(event.target.value))}>{Array.from({length:maxBitmapLevels},(_,level)=><option value={level} key={level}>Level {level}</option>)}</select></label>}
      <button onClick={()=>chooseControl(null,true)}>Screen properties</button>
      <button onClick={showProperties}>View properties ↓</button>
      {overlap&&<div className="hmiOverlapChoices" role="group" aria-label="Controls at this point"><b>Controls at this point · {overlap.side?newLabel:baseLabel}</b><span>Choose an object to view its properties:</span>{overlap.ids.map(id=>{const control=layouts[overlap.side]?.layers.flatMap(layer=>layer.controls).find(control=>control.id===id);return control&&<button type="button" key={id} aria-pressed={selected===id} onClick={()=>chooseControl(id,true)}>{control.name} <small>{control.class}</small></button>})}<button type="button" aria-label="Close control chooser" onClick={()=>setOverlap(null)}>Close</button></div>}
    </div>
    <div className="hmiPreviewNote">Base and Developed scrolling is linked. Click a control, then View properties below. Overlapping objects appear under Controls at this point; use Control to select any dropdown, numeric field or hotspot, including unchanged controls. Referenced bitmaps are displayed when their files are available. Released / Pressed and touchpad levels select configured images; live indexes, values and visibility are not simulated.</div>
    <div className="hmiPreviewLegend">{Object.entries(colors).map(([status,color])=><span key={status}><i style={{background:color}}>{symbol[status]}</i>{status==='unchanged'?'Same':status[0].toUpperCase()+status.slice(1)}</span>)}</div>
    <div className="hmiPreviewPair">
      {layouts.map((layout,index)=>{const bitmap=selectBitmap(layout?.bitmaps,bitmapState,bitmapLevel,language);const asset=bitmap?.asset_id?layout?.bitmap_assets?.[bitmap.asset_id]:undefined;return <section key={index} className={`hmiPreviewSide ${index?'developed':'base'}`}>
        <header><b>{index?newLabel:baseLabel}</b><span>{layout?`${layout.name} · ${layout.width} × ${layout.height}`:'Screen not present'}</span></header>
        {layout?<div className="hmiPreviewCanvasScroll" style={{height:canvasHeight}} ref={screenScroll.refs[index]} onScroll={screenScroll.onScroll(index)} tabIndex={0} aria-label={`${index?newLabel:baseLabel} screen scroll area`}>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${layout.width} ${layout.height}`} width={zoom==='fit'?'100%':layout.width*Number(zoom)} style={{display:'block',aspectRatio:`${layout.width}/${layout.height}`,minWidth:zoom==='fit'?0:layout.width*Number(zoom)}} aria-label={`${index?newLabel:baseLabel} HMI screen layout`}>
            <rect width={layout.width} height={layout.height} fill={paletteColor(layout,layout.properties.BackColor,'#f5f8fb')} onClick={()=>chooseControl(null)}/>
            {asset?.data_uri&&<image className="hmiPreviewBitmap hmiPreviewBackgroundBitmap" href={asset.data_uri} width={layout.width} height={layout.height} preserveAspectRatio="none" onClick={()=>chooseControl(null)}><title>{bitmapLabel(bitmap)}</title></image>}
            {bitmap&&!asset&&<text x={12} y={22} fontSize={12} fill="#975719">{`Bitmap unavailable: ${bitmapLabel(bitmap)}`}</text>}
            {visiblePreviewLayers(layout.layers,layerFilter).map(l=><g key={l.id} transform={`translate(${l.left} ${l.top})`}>
              {l.controls.map(c=><ControlBox key={c.id} control={c} layout={layout} language={language} bitmapState={bitmapState} selected={selected===c.id} names={names} fontScale={fontScale} onSelect={event=>pickControl(layout,l,c,index,event)}/>)}</g>)}
          </svg>
        </div>:<div className="hmiPreviewMissing">This screen is absent from this project.</div>}
        {bitmap&&<p className="hmiPreviewNote">{bitmapState==='pressed'?'Pressed':'Released'} bitmap: <b>{bitmapLabel(bitmap)}</b>{bitmap.index!==undefined?` · index ${bitmap.index}`:''}{!asset?` · ${bitmap.message||'Image not available'}`:''}</p>}
        {layout?.warnings?.map((w,i)=><p className="hmiPreviewNote" key={i}>{w}</p>)}
      </section>})}
    </div>
    <ResizeHandle height={canvasHeight} onChange={setCanvasHeight}/>
    <div className="hmiPreviewInspector" ref={inspectorRef}>
      <div className="hmiInspectorHeading"><h3>{selected?`Control properties: ${selected}`:'Screen properties'}</h3><button onClick={()=>previewRef.current?.scrollTo({top:0,behavior:'smooth'})}>Back to screens ↑</button></div>
      <HmiPropertyComparison base={properties[0]} developed={properties[1]} baseLabel={baseLabel} newLabel={newLabel} contextKey={`${baseLabel}:${newLabel}:${layouts[0]?.name}:${layouts[1]?.name}:${selected||'screen'}`} skipLayout={skipLayout} baseMissing={!!selected&&!controls[0]} newMissing={!!selected&&!controls[1]}/>
    </div>
  </div>;
}
