#!/usr/bin/env bash
# start.sh — one-click launcher for OpenSore (macOS/Linux)
#
# What this does, in order:
#   1. Pull latest changes from the current git branch
#   2. Re-install dependencies only if pyproject.toml / uv.lock changed since last run
#   3. Start the web UI (FastAPI on http://localhost:8000/ui) in the background
#   4. Open the web UI in your default browser
#   5. Launch the interactive CLI in this terminal window
#
# Requirements: git, uv  (Python and deps are managed by uv automatically)
# Install uv if needed:  curl -LsSf https://astral.sh/uv/install.sh | sh

set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  BOLD=$'\033[1m'; RESET=$'\033[0m'
  GREEN=$'\033[32m'; YELLOW=$'\033[33m'; CYAN=$'\033[36m'; RED=$'\033[31m'
else
  BOLD=''; RESET=''; GREEN=''; YELLOW=''; CYAN=''; RED=''
fi
info()    { printf "%s %s%s\n"    "${CYAN}→${RESET}"  "$*" "${RESET}"; }
success() { printf "%s %s%s\n"    "${GREEN}✓${RESET}" "$*" "${RESET}"; }
warn()    { printf "%s %s%s\n"    "${YELLOW}⚠${RESET}" "$*" "${RESET}"; }
fatal()   { printf "%s %s%s\n\n" "${RED}✗${RESET}"   "$*" "${RESET}" >&2; exit 1; }
banner()  { printf "\n%s%s%s\n\n" "${BOLD}" "$*" "${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

WEB_PORT=8000
WEB_URL="http://localhost:${WEB_PORT}/ui"
STAMP_FILE=".opensore_install_stamp"

banner "OpenSore — starting up"

# ── 1. Check prerequisites ───────────────────────────────────────────────────
info "Checking prerequisites..."

if ! command -v git >/dev/null 2>&1; then
  fatal "git not found. Install from https://git-scm.com"
fi

if ! command -v uv >/dev/null 2>&1; then
  fatal "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh\n       Then restart your terminal and run this script again."
fi

success "Prerequisites OK (git $(git --version | awk '{print $3}'), uv $(uv --version | awk '{print $2}'))"

# ── 2. Pull latest from git ───────────────────────────────────────────────────
info "Checking for updates..."

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ]; then
  warn "Not on a named branch — skipping git pull."
else
  REMOTE=$(git remote 2>/dev/null | head -1)
  if [ -z "$REMOTE" ]; then
    warn "No git remote configured — skipping pull."
  else
    # Fetch quietly; only pull if we're behind
    git fetch "$REMOTE" "$BRANCH" --quiet 2>/dev/null || warn "Could not reach remote — continuing with local copy."
    LOCAL=$(git rev-parse HEAD)
    REMOTE_REF=$(git rev-parse "${REMOTE}/${BRANCH}" 2>/dev/null || echo "$LOCAL")
    if [ "$LOCAL" != "$REMOTE_REF" ]; then
      info "New commits available — pulling..."
      git pull --ff-only "$REMOTE" "$BRANCH" || {
        warn "Auto-pull failed (possible local changes). Run 'git pull' manually if needed."
      }
      success "Updated to $(git rev-parse --short HEAD)"
    else
      success "Already up to date ($(git rev-parse --short HEAD))"
    fi
  fi
fi

# ── 3. Install / update dependencies (only when lockfile changed) ─────────────
info "Checking dependencies..."

# Compute a hash of the files that drive the install
CURRENT_HASH=$(cat pyproject.toml uv.lock 2>/dev/null | sha256sum | awk '{print $1}')
STORED_HASH=$(cat "$STAMP_FILE" 2>/dev/null || echo "")

if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
  info "Dependencies changed — running uv sync (this may take a minute on first run)..."
  uv sync --frozen --extra dev 2>&1 | grep -v "^$" || fatal "uv sync failed. Check error above."
  uv run python -m app.analytics.install 2>/dev/null || true
  echo "$CURRENT_HASH" > "$STAMP_FILE"
  success "Dependencies installed/updated"
else
  success "Dependencies up to date (no changes to pyproject.toml or uv.lock)"
fi

# ── 4. Check if web server port is already in use ─────────────────────────────
WEB_PID_FILE=".opensore_web.pid"
WEB_ALREADY_RUNNING=false

if [ -f "$WEB_PID_FILE" ]; then
  OLD_PID=$(cat "$WEB_PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    warn "Web server already running (PID $OLD_PID) — reusing it."
    WEB_ALREADY_RUNNING=true
  else
    rm -f "$WEB_PID_FILE"
  fi
fi

if ! $WEB_ALREADY_RUNNING; then
  if lsof -ti:"$WEB_PORT" >/dev/null 2>&1; then
    warn "Port $WEB_PORT is already in use by another process — web UI may already be up."
    WEB_ALREADY_RUNNING=true
  fi
fi

# ── 5. Start web UI in background ─────────────────────────────────────────────
if ! $WEB_ALREADY_RUNNING; then
  info "Starting web UI on ${WEB_URL} ..."
  uv run uvicorn app.webapp:app \
    --host 127.0.0.1 \
    --port "$WEB_PORT" \
    --log-level warning \
    > /tmp/opensore_web.log 2>&1 &
  WEB_PID=$!
  echo "$WEB_PID" > "$WEB_PID_FILE"

  # Wait up to 8 seconds for the server to accept connections
  READY=false
  for i in $(seq 1 16); do
    sleep 0.5
    if curl -s --max-time 1 "http://127.0.0.1:${WEB_PORT}/ok" >/dev/null 2>&1; then
      READY=true
      break
    fi
    # Check the process didn't die
    if ! kill -0 "$WEB_PID" 2>/dev/null; then
      fatal "Web server failed to start. Check logs: /tmp/opensore_web.log"
    fi
  done

  if $READY; then
    success "Web UI ready at ${WEB_URL}"
  else
    warn "Web server started (PID $WEB_PID) but didn't respond in 8s — opening browser anyway."
  fi
fi

# ── 6. Open browser ───────────────────────────────────────────────────────────
info "Opening browser..."
if command -v open >/dev/null 2>&1; then        # macOS
  open "$WEB_URL" 2>/dev/null || true
elif command -v xdg-open >/dev/null 2>&1; then  # Linux
  xdg-open "$WEB_URL" 2>/dev/null || true
else
  info "Visit the web UI at: ${WEB_URL}"
fi

# ── 7. Graceful shutdown on exit ──────────────────────────────────────────────
cleanup() {
  if [ -f "$WEB_PID_FILE" ]; then
    WEB_PID=$(cat "$WEB_PID_FILE")
    if kill -0 "$WEB_PID" 2>/dev/null; then
      info "Stopping web server (PID $WEB_PID)..."
      kill "$WEB_PID" 2>/dev/null || true
    fi
    rm -f "$WEB_PID_FILE"
  fi
  printf "\n%sDone. Goodbye!%s\n" "${BOLD}" "${RESET}"
}
trap cleanup EXIT INT TERM

# ── 8. Launch interactive CLI (foreground — this is your TUI) ─────────────────
printf "\n%s─────────────────────────────────────────────────────────%s\n" "${CYAN}" "${RESET}"
printf "%s Web UI → %s   (running in background)%s\n" "${CYAN}" "${WEB_URL}" "${RESET}"
printf "%s Logs   → /tmp/opensore_web.log%s\n" "${CYAN}" "${RESET}"
printf "%s Press Ctrl+C to stop everything and exit%s\n" "${CYAN}" "${RESET}"
printf "%s─────────────────────────────────────────────────────────%s\n\n" "${CYAN}" "${RESET}"

exec uv run opensore
