// On Vercel the demo is always the static recording: no backend, no Fly.io.
// Set here rather than only in vercel.json because `NEXT_PUBLIC_*` values are
// inlined at build time, and a leftover NEXT_PUBLIC_API_BASE in the Vercel
// dashboard was winning over vercel.json and baking a dead backend URL into
// the bundle. Next reads process.env after this file runs, so this is final.
if (process.env.VERCEL) {
  process.env.NEXT_PUBLIC_SNAPSHOT = '1';
  process.env.NEXT_PUBLIC_API_BASE = '';
}

/**
 * Three deployment shapes from one codebase.
 *
 * A container host runs the standalone server. Vercel builds the recording,
 * forced above. GitHub Pages has no server at all, so there the recorded
 * build exports to plain files -- which it can, because every route is
 * already static and the only data source is the JSON under public/snapshot.
 *
 * Pages serves a project site from a subpath, so the export also needs a
 * basePath, and anything that builds a URL by hand has to respect it (see
 * SNAPSHOT_ROOT in lib/api.ts).
 */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
const staticExport = process.env.NEXT_STATIC_EXPORT === '1';

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: staticExport ? 'export' : 'standalone',
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  // No image optimiser without a server.
  ...(staticExport ? { images: { unoptimized: true } } : {}),
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: false },
  typescript: { ignoreBuildErrors: false },
};

export default nextConfig;
