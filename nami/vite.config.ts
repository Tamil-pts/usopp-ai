import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

export default defineConfig({
  base: '/nami/',
  plugins: [react(), tailwindcss()],
  build: {outDir: '../dist/nami', emptyOutDir: true, sourcemap: false},
  server: {proxy: {'/api': 'http://127.0.0.1:8200'}},
});
