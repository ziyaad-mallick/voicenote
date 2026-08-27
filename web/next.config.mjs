/** @type {import('next').NextConfig} */
const nextConfig = {
  // This app is self-contained; without this, Turbopack walks up past the repo
  // looking for a workspace root and warns about unrelated lockfiles.
  turbopack: { root: import.meta.dirname },
  // Fully static: no server, no API routes, no env vars. `next build` emits out/.
  output: 'export',
  // `next dev` otherwise writes AGENTS.md/CLAUDE.md into this directory.
  agentRules: false,
  images: { unoptimized: true },
};

export default nextConfig;
