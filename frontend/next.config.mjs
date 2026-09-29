/** @type {import('next').NextConfig} */
const nextConfig = {
  // Do not generate AGENTS.md / CLAUDE.md in the project on every `next dev`
  agentRules: false,
  // No floating dev tools badge over the interface
  devIndicators: false,
};

export default nextConfig;
