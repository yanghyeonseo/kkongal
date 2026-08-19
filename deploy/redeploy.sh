#!/usr/bin/env bash
# =============================================================================
# kkongal 재배포 스크립트 (가비아 서버 · Docker 없이 systemd + nginx).
#
#   ssh ubuntu@kkongal.cloud
#   ~/kkongal/deploy/redeploy.sh            # main 브랜치 최신으로 재배포
#   ~/kkongal/deploy/redeploy.sh deploy-gabia   # 특정 브랜치로 재배포
#
# 하는 일: git pull → 백엔드 의존성/마이그레이션/정적파일 → 프론트 빌드 배포 →
#          gunicorn 재시작 → 헬스체크.
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/kkongal}"
BRANCH="${1:-main}"
WEB_ROOT=/var/www/kkongal
STATIC_ROOT=/var/www/kkongal-static

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

say "코드 갱신 ($BRANCH)"
cd "$APP_DIR"
git fetch --prune origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

say "백엔드 의존성"
cd "$APP_DIR/backend"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

say "마이그레이션"
.venv/bin/python manage.py migrate --noinput

say "정적 파일 수집"
.venv/bin/python manage.py collectstatic --noinput
sudo mkdir -p "$STATIC_ROOT"
sudo rsync -a --delete "$APP_DIR/backend/staticfiles/" "$STATIC_ROOT/"
sudo chown -R www-data:www-data "$STATIC_ROOT"

say "프론트 빌드"
cd "$APP_DIR/frontend"
npm ci --no-audit --no-fund
npm run build
sudo mkdir -p "$WEB_ROOT"
sudo rsync -a --delete dist/ "$WEB_ROOT/"
sudo chown -R www-data:www-data "$WEB_ROOT"

say "서비스 재시작"
sudo systemctl restart kkongal
sudo systemctl reload nginx

say "헬스체크"
sleep 2
curl -fsS -H 'Host: kkongal.cloud' http://127.0.0.1/api/healthz/ && echo
sudo systemctl --no-pager --lines=0 status kkongal | head -5

say "완료"
