#!/usr/bin/env bash
# dev.sh — Run all services (backend + admin + tunnel) in separate terminal windows.
# Usage: ./dev.sh        — start all services
#        ./dev.sh stop   — stop all services

set -euo pipefail

# Colors for log prefixes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# --- Kill anything occupying our ports ---
kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}⚡ Killing processes on port $port: $pids${NC}"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 0.5
    fi
}

# --- Stop all services ---
stop_all() {
    echo -e "${RED}🛑 Stopping all services...${NC}"

    # Kill cloudflared by name (it doesn't use a fixed port)
    pkill -f "cloudflared tunnel" 2>/dev/null || true

    kill_port 8000
    kill_port 3001

    echo -e "${GREEN}✅ All services stopped.${NC}"
}

# --- Handle ./dev.sh stop ---
if [[ "${1:-}" == "stop" ]]; then
    stop_all
    exit 0
fi

# --- Detect terminal emulator ---
detect_terminal() {
    if command -v gnome-terminal &>/dev/null; then
        echo "gnome-terminal"
    elif command -v konsole &>/dev/null; then
        echo "konsole"
    elif command -v alacritty &>/dev/null; then
        echo "alacritty"
    elif command -v kitty &>/dev/null; then
        echo "kitty"
    elif command -v tilix &>/dev/null; then
        echo "tilix"
    elif command -v xterm &>/dev/null; then
        echo "xterm"
    else
        echo "none"
    fi
}

# Open a new terminal window with a title and command
open_terminal() {
    local title="$1"
    shift
    local cmd="$*"

    local term
    term=$(detect_terminal)

    case "$term" in
        gnome-terminal)
            gnome-terminal --title="$title" -- bash -c "$cmd; echo ''; echo 'Press Enter to close...'; read -r"
            ;;
        konsole)
            konsole --new-tab -p tabtitle="$title" -e bash -c "$cmd; echo ''; echo 'Press Enter to close...'; read -r" &
            ;;
        alacritty)
            alacritty -t "$title" -e bash -c "$cmd; echo ''; echo 'Press Enter to close...'; read -r" &
            ;;
        kitty)
            kitty -T "$title" bash -c "$cmd; echo ''; echo 'Press Enter to close...'; read -r" &
            ;;
        tilix)
            tilix -t "$title" -a session-add-right -e bash -c "$cmd; echo ''; echo 'Press Enter to close...'; read -r" &
            ;;
        xterm)
            xterm -T "$title" -e bash -c "$cmd; echo ''; echo 'Press Enter to close...'; read -r" &
            ;;
        *)
            echo -e "${RED}❌ No supported terminal emulator found.${NC}"
            echo -e "${YELLOW}   Install one of: gnome-terminal, konsole, alacritty, kitty, tilix, xterm${NC}"
            exit 1
            ;;
    esac
}

# Kill existing processes on our ports
echo -e "${CYAN}🔧 Checking for existing processes...${NC}"
kill_port 8000
kill_port 3001

# --- Start Backend in a new window ---
# Force the local dev env explicitly. ENVIRONMENT defaults to "production"
# (fail-closed), and the __DEV_MODE__ guard-auth bypass only runs when BOTH
# ENVIRONMENT=dev AND DEV_AUTH_BYPASS_ENABLED=true. Exporting here (env vars
# take priority over backend/.env) guarantees ./dev.sh always runs as dev.
echo -e "${GREEN}🚀 Starting Backend (port 8000) in a new window...${NC}"
open_terminal "🔧 Backend" \
    "cd '$PROJECT_ROOT/backend' && source .venv/bin/activate && export ENVIRONMENT=dev DEV_AUTH_BYPASS_ENABLED=true && exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# --- Wait for Backend to be ready ---
echo -e "${CYAN}⏳ Waiting for backend to be ready...${NC}"
MAX_WAIT=30
WAITED=0
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo -e "${RED}❌ Backend did not become ready within ${MAX_WAIT}s${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✅ Backend is ready (took ${WAITED}s)${NC}"

# --- Start Admin Frontend in a new window ---
# Serve the PRODUCTION BUILD via `vite preview`, not the dev server. The dev
# server hands out the unbundled ESM module graph (dozens of separate requests),
# which Telegram's in-app WebView on older Android failed to load → blank guard
# page. `vite build` produces a single transpiled bundle that the WebView parses
# reliably. `noCacheWebApp` + `preview.proxy` (see vite.config.js) still apply.
echo -e "${GREEN}🚀 Building & serving Admin Dashboard (port 3001) in a new window...${NC}"
open_terminal "🎨 Admin" \
    "cd '$PROJECT_ROOT/frontend/admin' && npm run build && exec npm run preview"

# --- Start Cloudflare Tunnel in a new window ---
if command -v cloudflared &>/dev/null; then
    echo -e "${GREEN}🌐 Starting Cloudflare Tunnel in a new window...${NC}"
    open_terminal "🌐 Tunnel" \
        "exec cloudflared tunnel run ilutzim-app"
else
    echo -e "${YELLOW}⚠️  cloudflared not found — skipping tunnel${NC}"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ All services launched in separate windows!${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "  Backend API:     ${GREEN}http://localhost:8000${NC}"
echo -e "  Admin Dashboard: ${GREEN}http://localhost:3001${NC}"
echo -e "  Tunnel:          ${GREEN}https://app.example.com${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo -e "  To stop all:  ${RED}./dev.sh stop${NC}  (or close each window)"
echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
echo ""