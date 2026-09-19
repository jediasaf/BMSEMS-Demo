# ---- EcoTwin AI :: web -----------------------------------------------------
# Multi-stage: the runtime carries the Next.js standalone output only, so the
# final image has no toolchain and no node_modules tree.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked in at build time: Next.js inlines NEXT_PUBLIC_* into the client bundle.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -g 10001 -S ecotwin && adduser -u 10001 -S ecotwin -G ecotwin
COPY --from=build --chown=ecotwin:ecotwin /app/.next/standalone ./
COPY --from=build --chown=ecotwin:ecotwin /app/.next/static ./.next/static
COPY --from=build --chown=ecotwin:ecotwin /app/public ./public
USER ecotwin
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/" >/dev/null || exit 1
CMD ["node", "server.js"]
