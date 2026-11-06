import type {Row} from '../intelligence/api';
export function SymbolArt({asset,fill='none',stroke='currentColor',width=1.5}:{asset:Row;fill?:string;stroke?:string;width?:number}){
 const props={fill,stroke,strokeWidth:width,vectorEffect:'non-scaling-stroke' as const};
 if(asset.shape==='path')return <path d={asset.path} {...props} fill="none"/>;
 if(asset.shape==='ellipse')return <ellipse cx="50" cy="50" rx="49" ry="49" {...props}/>;
 if(asset.shape==='diamond')return <polygon points="50,1 99,50 50,99 1,50" {...props}/>;
 if(asset.shape==='io')return <polygon points="12,1 99,1 87,99 1,99" {...props}/>;
 if(asset.shape==='document')return <path d="M1 1 H99 V85 Q75 110 50 90 Q25 70 1 90 Z" {...props}/>;
 return <><rect x="1" y="1" width="98" height="98" rx={asset.shape==='roundrect'?35:5} {...props}/>{asset.shape==='subprocess'&&<path d="M10 1 V99 M90 1 V99" {...props} fill="none"/>}</>;
}
