#!/usr/bin/env bash
# Deploy the EcoTwin backend and prove it works, or say exactly what is missing.
#
# Everything this needs is committed: the Dockerfile, fly.toml and render.yaml
# already carry the sizes measured from a real run of the image. The one thing
# that cannot live in a repository is the credential, so that is the only
# question this script asks -- and it asks it before doing any work.
#
#   FLY_API_TOKEN=...   bash scripts/deploy_backend.sh          # Fly.io
#   RENDER_API_KEY=...  bash scripts/deploy_backend.sh --render # Render
#
# On success it prints the backend URL and the single command that wires the
# frontend to it.
set -euo pipefail

APP="${ECOTWIN_APP_NAME:-ecotwin-api}"
TARGET="fly"
[[ "${1:-}" == "--render" ]] && TARGET="render"

say() { printf '\n\033[36m==\033[0m %s\n' "$*"; }
die() { printf '\n\033[31m!!\033[0m %s\n' "$*" >&2; exit 1; }

# -- 1. the credential ------------------------------------------------------
if [[ "$TARGET" == "fly" ]]; then
  FLY="$(command -v flyctl || command -v fly || echo "$HOME/.fly/bin/flyctl")"
  [[ -x "$FLY" ]] || die "flyctl not found. Install it: curl -L https://fly.io/install.sh | sh"
  if [[ -z "${FLY_API_TOKEN:-}" ]] && ! "$FLY" auth whoami >/dev/null 2>&1; then
    die "No Fly.io credential.
  Either:  export FLY_API_TOKEN=\$(flyctl tokens create deploy --name ecotwin)
  Or:      flyctl auth login
  Then re-run this script."
  fi
else
  [[ -n "${RENDER_API_KEY:-}" ]] || die "No Render credential. Set RENDER_API_KEY and re-run."
fi

# -- 2. deploy --------------------------------------------------------------
if [[ "$TARGET" == "fly" ]]; then
  say "Deploying $APP to Fly.io (1 GB, one always-on machine)"
  "$FLY" apps create "$APP" 2>/dev/null || true
  "$FLY" deploy --config fly.toml --app "$APP" --ha=false
  BASE="https://${APP}.fly.dev"
else
  say "Render deploys from render.yaml on push."
  echo "  1. Connect this repository at https://dashboard.render.com/blueprints"
  echo "  2. Render reads render.yaml: Docker runtime, Standard plan, /healthz check"
  echo "  3. Re-run with ECOTWIN_API_BASE=<the URL Render assigns> to verify it"
  BASE="${ECOTWIN_API_BASE:-}"
  [[ -n "$BASE" ]] || exit 0
fi

# -- 3. prove it ------------------------------------------------------------
say "Verifying $BASE"
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 10 "$BASE/healthz" >/dev/null 2>&1; then break; fi
  [[ $attempt -eq 30 ]] && die "$BASE/healthz never answered. Check the platform logs."
  sleep 5
done
echo "  /healthz            $(curl -fsS --max-time 10 "$BASE/healthz")"
echo "  /health components  $(curl -fsS --max-time 30 "$BASE/health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["components"])')"

READY="$(curl -fsS --max-time 120 "$BASE/interview/verify" \
  | python3 -c 'import json,sys; b=json.load(sys.stdin); print("READY" if b["ready"] else "NOT READY: "+", ".join(b["failed"]))')"
echo "  /interview/verify   $READY"
[[ "$READY" == "READY" ]] || die "The backend is up but the demo is not ready. Fix the checks above first."

# -- 4. the one remaining step ---------------------------------------------
say "Backend live: $BASE"
cat <<NEXT

Wire the frontend to it (NEXT_PUBLIC_API_BASE is inlined at build time, so
this needs a redeploy, not just an environment edit):

    cd apps/web
    vercel env rm NEXT_PUBLIC_API_BASE production --yes 2>/dev/null || true
    echo -n "$BASE" | vercel env add NEXT_PUBLIC_API_BASE production
    vercel --prod

Then run the production end-to-end suite against both:

    E2E_BASE_URL=https://ecotwin-ai-zeta.vercel.app \\
    E2E_API_BASE=$BASE \\
      npx playwright test --config apps/web/playwright.config.ts

If the frontend origin is not already in the backend's CORS allowlist:

    flyctl secrets set ECOTWIN_CORS_ORIGINS=https://ecotwin-ai-zeta.vercel.app --app $APP
NEXT
