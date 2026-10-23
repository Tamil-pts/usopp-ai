import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const frontendPort = Number(process.env.USOPP_FRONTEND_PORT || env.USOPP_FRONTEND_PORT || 8201);
  const apiPort = Number(process.env.USOPP_API_PORT || env.USOPP_API_PORT || 8200);
  for (const port of [frontendPort, apiPort]) {
    if (!Number.isInteger(port) || port < 8200 || port > 8500) throw new Error('uSOPp application ports must be within 8200–8500.');
  }
  if (frontendPort === apiPort) throw new Error('Development frontend and backend must use different application ports.');
  return {
    plugins: [react(),{
      name:'usopp-frontend-build-info',
      writeBundle(output,bundle){
        const entry=Object.values(bundle).find(item=>item.type==='chunk'&&item.isEntry);
        if(!entry||!output.dir)throw new Error('The main interface build has no entry asset.');
        const version=JSON.parse(readFileSync(resolve('package.json'),'utf8')).version;
        const entrySha256=createHash('sha256').update(readFileSync(resolve(output.dir,entry.fileName))).digest('hex');
        writeFileSync(resolve(output.dir,'build-info.json'),JSON.stringify({version,entryFile:entry.fileName,entrySha256,
          sourceCommit:process.env.USOPP_SOURCE_COMMIT||null,builtAt:new Date().toISOString()},null,2)+'\n');
      }
    }],
    resolve: {dedupe: ['react', 'react-dom']},
    build: { sourcemap: false, minify: 'esbuild' },
    server: {
      port: frontendPort,
      host: '127.0.0.1',
      strictPort:true,
      proxy: { '/api': `http://127.0.0.1:${apiPort}`, '/nami': `http://127.0.0.1:${apiPort}` }
    }
  };
});
