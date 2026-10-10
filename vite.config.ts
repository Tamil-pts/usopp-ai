import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const frontendPort = Number(process.env.USOPP_FRONTEND_PORT || env.USOPP_FRONTEND_PORT || 8201);
  const apiPort = Number(process.env.USOPP_API_PORT || env.USOPP_API_PORT || 8200);
  for (const port of [frontendPort, apiPort]) {
    if (!Number.isInteger(port) || port < 8200 || port > 8500) throw new Error('uSOPp application ports must be within 8200–8500.');
  }
  if (frontendPort === apiPort) throw new Error('Development frontend and backend must use different application ports.');
  return {
    plugins: [react()],
    build: { sourcemap: false, minify: 'esbuild' },
    server: {
      port: frontendPort,
      host: '127.0.0.1',
      strictPort:true,
      proxy: { '/api': `http://127.0.0.1:${apiPort}`, '/nami': `http://127.0.0.1:${apiPort}` }
    }
  };
});
