import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') } } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    // Serialised pending #38. Run in parallel the suite fails roughly 9 times in 20, with a
    // different test failing each run across unrelated files; serialised it is clean. The cause
    // is not yet found, so this is a stated workaround rather than a fix — a green `make check`
    // that only happens half the time is worse than a slower one that always means something.
    fileParallelism: false,
  },
})
