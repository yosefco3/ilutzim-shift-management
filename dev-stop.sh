#!/usr/bin/env bash
# dev-stop.sh — Stop all dev services (backend + admin + tunnel).
# Usage: ./dev-stop.sh
#        (or: ./dev.sh stop)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo -e "${RED}🛑 Stopping all services...${NC}"

# Kill cloudflared by name
pkill -f "cloudflared tunnel" 2>/dev/null && echo -e "  ${YELLOW}⚡ Killed cloudflared tunnel${NC}" || true

# Kill processes on each port
for port in 8000 3001; do
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo -e "  ${YELLOW}⚡ Killing processes on port $port: $pids${NC}"
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
done

sleep 0.5

# Verify everything is dead
ALL_CLEAR=true
for port in 8000 3001; do
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo -e "  ${RED}⚠️  Port $port still occupied by: $pids${NC}"
        ALL_CLEAR=false
    fi
done

if pgrep -f "cloudflared tunnel" &>/dev/null; then
    echo -e "  ${RED}⚠️  cloudflared still running${NC}"
    ALL_CLEAR=false
fi

if $ALL_CLEAR; then
    echo -e "${GREEN}✅ All services stopped. All ports clear.${NC}"
else
    echo -e "${YELLOW}⚠️  Some processes may still be running. Try: ./dev-stop.sh again${NC}"
fi