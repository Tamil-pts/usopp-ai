import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

export default defineConfig({
  base: '/nami/',
  plugins: [react(), tailwindcss()],
  // Shared workspace components live outside nami and otherwise load the
  // parent node_modules copy of React, which has a different hook dispatcher.
  resolve: {dedupe: ['react', 'react-dom']},
  build: {outDir: '../dist/nami', emptyOutDir: true, sourcemap: false},
  server: {proxy: {'/api': 'http://127.0.0.1:8200'}},
});
