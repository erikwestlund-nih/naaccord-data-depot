import { defineConfig } from 'vite';
import { resolve } from 'path';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [
    tailwindcss(),
  ],
  build: {
    outDir: 'static',
    manifest: true,
    emptyOutDir: false, // Don't wipe static/icons/
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'resources/js/app.js'),
        styles: resolve(__dirname, 'resources/css/app.css')
      }
    }
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    hmr: {
      host: 'localhost',
      port: 3000,
      protocol: 'ws'
    },
    watch: {
      usePolling: true
    }
  }
});