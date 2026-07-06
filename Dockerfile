# ── Combined production image for Railway (single service) ──────────────────
# Builds the React frontend, then serves it from FastAPI (same origin).
# Build context MUST be the repo root.

# ── Stage 1: build the frontend ──
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/admin/package*.json ./
RUN npm ci
COPY frontend/admin/ ./
# Part B hidden in production; single-origin API base (no /api proxy in prod).
ARG VITE_SCHEDULE_BUILDER_ENABLED=false
ARG VITE_API_URL=
# Stage 3 (attendance) UI — default ON so the nav/pages ship visible; pair
# with the backend ATTENDANCE_ENABLED env var (both must be on, like part B).
ARG VITE_ATTENDANCE_ENABLED=true
# סידור בפועל (actual schedule) UI — default ON; pair with the backend
# ACTUAL_SCHEDULE_ENABLED env var (which switches the comparison source).
ARG VITE_ACTUAL_SCHEDULE_ENABLED=true
RUN VITE_SCHEDULE_BUILDER_ENABLED=$VITE_SCHEDULE_BUILDER_ENABLED \
    VITE_API_URL=$VITE_API_URL \
    VITE_ATTENDANCE_ENABLED=$VITE_ATTENDANCE_ENABLED \
    VITE_ACTUAL_SCHEDULE_ENABLED=$VITE_ACTUAL_SCHEDULE_ENABLED \
    npm run build

# ── Stage 2: python dependencies ──
FROM python:3.12-slim AS pybuild
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 3: runtime ──
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=pybuild /install /usr/local
COPY backend/ /app/
# Built frontend served by FastAPI (app/main.py looks for ../frontend_dist).
COPY --from=frontend /fe/dist /app/frontend_dist
COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Belt-and-suspenders for the weekly rollover: the real fix is today_il()/now_il()
# (SCHEDULER_TIMEZONE), but pin the container clock too so any forgotten naive
# date logic or third-party lib also sees Israel time, not UTC (B-3).
ENV TZ=Asia/Jerusalem

ENTRYPOINT ["/docker-entrypoint.sh"]
# Bind to Railway's injected $PORT (default 8000 for local runs).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
