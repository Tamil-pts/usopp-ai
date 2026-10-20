import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: fileURLToPath(new URL('./ui', import.meta.url)),
  base: '/virtual-plc/',
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom'] },
  build: { outDir: '../dist', emptyOutDir: true, sourcemap: false },
  server: {
    host: '127.0.0.1', port: 8203, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8200' },
  },
});
