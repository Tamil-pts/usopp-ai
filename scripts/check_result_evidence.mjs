import {build} from 'esbuild';
import {mkdir,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
const out='.build/result-evidence-review';
await mkdir(out,{recursive:true});
for(const name of ['result_evidence_review.test','readable_findings_check']){
 const outfile=`${out}/${name}.cjs`;
 await build({entryPoints:[`tests/${name}.tsx`],outfile,bundle:true,platform:'node',format:'cjs',packages:'external',jsx:'automatic',loader:{'.css':'empty'}});
 const result=spawnSync(process.execPath,[outfile],{stdio:'inherit'});
 if(result.status!==0)process.exit(result.status||1);
}
if(process.argv.includes('--browser-fixture')){
 await build({entryPoints:['tests/result_evidence_review_browser.tsx'],outfile:`${out}/browser.js`,bundle:true,platform:'browser',format:'esm',jsx:'automatic'});
 await writeFile(`${out}/index.html`,'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="browser.css"><style>body{min-width:0}main{overflow-wrap:anywhere}</style></head><body><div id="root"></div><script type="module" src="browser.js"></script></body></html>');
}
