/** @type {import('next').NextConfig} */
const nextConfig = {
  // Do not generate AGENTS.md / CLAUDE.md in the project on every `next dev`
  agentRules: false,
};

export default nextConfig;
