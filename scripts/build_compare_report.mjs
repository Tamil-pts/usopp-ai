import {build} from 'esbuild';
import {resolve} from 'node:path';
import {mkdir} from 'node:fs/promises';

const directory=resolve('dist/report-assets');
await mkdir(directory,{recursive:true});
await build({entryPoints:[resolve('src/features/compare/report/HmiReport.tsx')],outfile:resolve(directory,'hmi-report.js'),
 bundle:true,minify:true,format:'iife',platform:'browser',target:'es2020',jsx:'automatic',charset:'utf8',legalComments:'inline',
 define:{'process.env.NODE_ENV':'"production"'},plugins:[{name:'standalone-report-storage',setup(builder){
  builder.onResolve({filter:/\/userStorage$/},()=>({path:resolve('src/features/compare/report/storage.ts')}));
 }}]});
console.log('Built the standalone MatchView HMI report viewer.');
