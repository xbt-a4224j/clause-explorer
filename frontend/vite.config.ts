import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The platform's frontend half, alongside its Python wheel in vendor/. Written there by
// semantic-quorum's scripts/sync-into.sh, so `make platform-sync` is a prerequisite of a build
// exactly as it is for the backend.
//
// An alias to source rather than a built package: the domain's own Vite build compiles it, so
// there is no second build step to keep in step and no dist/ to go stale. The cost is that the
// platform's TSX has to be compatible with the domain's toolchain — which it is, because they
// are the same toolchain, and the day they are not is the day this needs a real build.
const quorumUi = fileURLToPath(new URL('./vendor/quorum-ui/src', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@quorum/ui': quorumUi } },
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
