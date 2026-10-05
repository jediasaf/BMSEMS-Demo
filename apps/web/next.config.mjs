// On Vercel the demo is always the static recording: no backend, no Fly.io.
// Set here rather than only in vercel.json because `NEXT_PUBLIC_*` values are
// inlined at build time, and a leftover NEXT_PUBLIC_API_BASE in the Vercel
// dashboard was winning over vercel.json and baking a dead backend URL into
// the bundle. Next reads process.env after this file runs, so this is final.
if (process.env.VERCEL) {
  process.env.NEXT_PUBLIC_SNAPSHOT = '1';
  process.env.NEXT_PUBLIC_API_BASE = '';
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: false },
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
