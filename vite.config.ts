import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  plugins: [],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './assets/js'),
    },
  },
  base: '/static/',
  build: {
    manifest: true,
    outDir: path.resolve(__dirname, './static'),
    emptyOutDir: false,
    rollupOptions: {
      input: {
        'site-base-css': path.resolve(__dirname, './assets/css/site-base.css'),
        'site-tailwind-css': path.resolve(__dirname, './assets/css/site-tailwind.css'),
        'site': path.resolve(__dirname, './assets/js/site.js'),
        'app': path.resolve(__dirname, './assets/js/app.js'),
      },
      output: {
        entryFileNames: `js/[name]-bundle.js`,
        chunkFileNames: `js/[name]-[hash].js`,
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            let baseName = path.basename(assetInfo.name, '.css');
            baseName = baseName.replace(/\.[0-9a-fA-F]{8}$/, '');
            return `css/${baseName}.css`;
          }
          return `assets/[name]-[hash][extname]`;
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    hmr: {},
  },
});
