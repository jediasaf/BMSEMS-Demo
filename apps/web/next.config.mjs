/**
 * Two deployment shapes from one codebase.
 *
 * A container host runs the standalone server. GitHub Pages has no server at
 * all, so the recorded build exports to plain files instead -- which it can,
 * because every route is already static and the only data source is the JSON
 * under public/snapshot. Pages serves a project site from a subpath, so the
 * export also needs a basePath, and anything that builds a URL by hand has to
 * respect it (see SNAPSHOT_ROOT in lib/api.ts).
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
