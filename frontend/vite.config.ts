import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import tailwindcss from '@tailwindcss/vite'; // Assuming this import is correct

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const isDev = mode === 'development';

  return {
    plugins: [tailwindcss(), react()].filter(Boolean),
    // In production the panel is served from HA's static path, so dynamically
    // imported chunks (e.g. the lazy-loaded scanner) must resolve from there.
    base: isDev ? '/' : '/homestead_inventory_static/',
    build: {
      outDir: '../custom_components/homestead_inventory/panel',
      cssCodeSplit: false,
      emptyOutDir: true,
      rollupOptions: {
        input: isDev
          ? resolve(__dirname, 'src/main.dev.tsx')
          : resolve(__dirname, 'src/panel-wrapper.tsx'),
        output: {
          entryFileNames: 'panel-wrapper.js',
          // Code-split: keep the heavy scanner (@zxing) in its own chunk that
          // only loads on demand. Flat names so HA's static path serves them.
          chunkFileNames: '[name]-[hash].js',
          assetFileNames: '[name]-[hash][extname]',
          inlineDynamicImports: isDev,
        },
      },
      chunkSizeWarningLimit: 1000,
    },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: `http://${env.VITE_HA_IP}:${env.VITE_HA_PORT}`,
          changeOrigin: true,
          secure: false,
          ws: true,
          configure: (proxy, _options) => {
            proxy.on('error', (err, _req, _res) => {
              console.log('proxy error', err);
            });
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              console.log('Sending Request:', req.method, req.url);
            });
            proxy.on('proxyRes', (proxyRes, req, _res) => {
              console.log('Received Response:', proxyRes.statusCode, req.url);
            });
          },
        },
      },
    },
  };
});
