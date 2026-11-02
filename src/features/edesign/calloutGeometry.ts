export function defaultCallout(box:number[],aspect=1,occupied:number[][]=[]):number[]{
 const [x0,y0,x1,y1]=box,gap=.025,w=.23,h=Math.max(.05,Math.min(.13,.055*aspect));
 const starts=[[x1+gap,y0],[x0-w-gap,y0],[x0,y1+gap],[x0,y0-h-gap],...[.025,.2,.4,.6,.8].flatMap(y=>[.015,.38,.75].map(x=>[x,y]))];
 const overlap=(a:number[],b:number[])=>Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]))/(w*h);
 return starts.map(([x,y],index)=>{x=Math.max(.01,Math.min(1-w-.01,x));y=Math.max(.01,Math.min(1-h-.01,y));const rect=[x,y,x+w,y+h];return {rect,score:100*overlap(rect,box)+60*occupied.reduce((n,r)=>n+overlap(rect,r),0)+Math.hypot(x+w/2-(x0+x1)/2,y+h/2-(y0+y1)/2)*.35+index*.003};}).sort((a,b)=>a.score-b.score)[0].rect;
}
function boundary(box:number[],towards:number[]):number[]{
 const [x0,y0,x1,y1]=box,cx=(x0+x1)/2,cy=(y0+y1)/2,dx=towards[0]-cx,dy=towards[1]-cy;
 const scale=Math.min(dx?(x1-x0)/2/Math.abs(dx):Infinity,dy?(y1-y0)/2/Math.abs(dy):Infinity);
 return Number.isFinite(scale)?[cx+dx*scale,cy+dy*scale]:[x1,cy];
}
export function calloutLeader(box:number[],label:number[]):number[][]{
 const center=(r:number[])=>[(r[0]+r[2])/2,(r[1]+r[3])/2],start=boundary(label,center(box)),tip=boundary(box,center(label));
 const knee=Math.abs(tip[0]-start[0])>=Math.abs(tip[1]-start[1])?[tip[0],start[1]]:[start[0],tip[1]];
 return Math.hypot(knee[0]-tip[0],knee[1]-tip[1])<1e-7?[start,tip]:[start,knee,tip];
}
export function moveMarkup(box:number[],label:number[]|null|undefined,dx:number,dy:number){
 const bounds=label?[Math.min(box[0],label[0]),Math.min(box[1],label[1]),Math.max(box[2],label[2]),Math.max(box[3],label[3])]:box;
 dx=Math.max(-bounds[0],Math.min(1-bounds[2],dx));dy=Math.max(-bounds[1],Math.min(1-bounds[3],dy));
 const shift=(r:number[])=>[r[0]+dx,r[1]+dy,r[2]+dx,r[3]+dy];
 return {box:shift(box),callout:label?shift(label):label};
}
