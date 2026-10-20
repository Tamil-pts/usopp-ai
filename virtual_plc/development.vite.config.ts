import { defineConfig, mergeConfig, loadEnv } from 'vite';
import baseConfig from '../vite.config';

// Reuse the working main React development frontend without changing its files.
export default defineConfig(async environment => {
  const base = typeof baseConfig === 'function' ? await baseConfig(environment) : baseConfig;
  const env = loadEnv(environment.mode, process.cwd(), '');
  const apiPort = Number(process.env.USOPP_API_PORT || env.USOPP_API_PORT || 8200);
  return mergeConfig(base, {
    optimizeDeps: {
      entries: ['index.html'], noDiscovery: true,
      include: ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime', 'react/jsx-dev-runtime', 'lucide-react'],
    },
    plugins: [{
      name: 'usopp-virtual-plc-navigation',
      transformIndexHtml: {
        order: 'post',
        handler(html) {
          // This classic script is served by the backend proxy, not compiled
          // as a React entry or warmed up as a filesystem module by Vite.
          return html.replace('</body>', '<script defer src="/virtual-plc/navigation.js"></script></body>');
        },
      },
    }],
    server: {
      proxy: {
        '/virtual-plc': `http://127.0.0.1:${apiPort}`,
        '/nami': {
          target: `http://127.0.0.1:${apiPort}`,
          bypass(request) {
            // The main app imports shared Nami parser source. Only the built
            // Nami interface belongs to the backend static-file proxy.
            if (/^\/nami\/(src|node_modules)\//.test(request.url || '')) return request.url;
          },
        },
      },
      // Imported PLC projects, AI weights and Python environments are not
      // frontend source. Avoid watching hundreds of thousands of their files.
      watch: {ignored: [
        '**/.build/**', '**/.venv/**', '**/.venv-training/**',
        '**/.usopp_exports/**', '**/.usopp_workspaces/**', '**/.pytest_cache/**',
        '**/artifacts/**', '**/logs/**', '**/local_ai/**', '**/dist/**',
        '**/distribution/**', '**/release/**', '**/backend/**',
        '**/python_engine/**', '**/knowledge/**',
      ]},
    },
  });
});
