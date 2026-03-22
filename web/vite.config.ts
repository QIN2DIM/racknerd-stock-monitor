import { copyFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

import { defineConfig, type Plugin } from 'vite';

function copyLatestJsonPlugin(): Plugin {
  const sourceFile = resolve(__dirname, '../data/latest.json');
  const targetDir = resolve(__dirname, 'dist/data');

  return {
    name: 'copy-latest-json',
    closeBundle() {
      mkdirSync(targetDir, { recursive: true });
      copyFileSync(sourceFile, resolve(targetDir, 'latest.json'));
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [copyLatestJsonPlugin()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.ts'],
  },
});
