#!/bin/bash
# ============================================================
# Nexent 一键修复脚本（在 WSL 里运行）
#
# 用途：Docker Desktop / WSL 重启后，容器报 Exited (127) 或登录不上时，
#       重建容器，让挂载点重新解析。
#
# 用法：
#   bash scripts/restart-nexent.sh          # 全量重建（推荐，约 1 分钟）
#   bash scripts/restart-nexent.sh --check  # 只看状态，不动任何东西
# ============================================================

set -u

DEPLOY_ROOT="${NEXENT_DEPLOY_ROOT:-/home/fate/nexent/deploy}"
COMPOSE_DIR="$DEPLOY_ROOT/docker/compose"
ENV_ARGS="--env-file docker/.env.generated --env-file env/.env"
PROJECT="-p nexent"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }
line()  { printf '%.0s─' {1..56}; echo; }

print_status() {
  line
  docker ps -a --format '{{.Names}}\t{{.Status}}' \
    | grep -E 'nexent-|supabase-' | sort \
    | awk -F'\t' '{printf "  %-24s %s\n", $1, $2}'
  line
  local bad
  bad=$(docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'nexent-|supabase-' | grep -cE 'Exited|Restarting')
  if [ "$bad" -gt 0 ]; then
    red "  有 $bad 个容器状态异常"
  else
    green "  全部正常"
  fi
}

# ---------- 只检查 ----------
if [ "${1:-}" = "--check" ]; then
  print_status
  exit 0
fi

# ---------- 前置检查 ----------
if ! command -v docker >/dev/null 2>&1; then
  red "找不到 docker 命令，请在 WSL 里运行本脚本"
  exit 1
fi

if [ ! -d "$COMPOSE_DIR" ]; then
  red "找不到 compose 目录：$COMPOSE_DIR"
  yellow "如果你的 Nexent 装在别处，先设置：export NEXENT_DEPLOY_ROOT=/你的路径/deploy"
  exit 1
fi

cd "$DEPLOY_ROOT" || exit 1

echo "修复前的状态："
print_status

# ---------- 1. 重建 supabase（登录用的） ----------
echo
yellow "[1/3] 重建登录服务（supabase）..."
docker compose $ENV_ARGS $PROJECT -f docker/compose/docker-compose-supabase.yml \
  up -d --force-recreate 2>&1 | grep -E "Started|Recreated|Error|error" | tail -10

# ---------- 2. 重建核心服务 ----------
echo
yellow "[2/3] 重建核心服务（config / runtime / postgres / data-process ...）..."
docker compose $ENV_ARGS $PROJECT -f docker/compose/docker-compose.prod.yml \
  up -d --force-recreate 2>&1 | grep -E "Started|Recreated|Error|error" | tail -20

# ---------- 3. 等健康 ----------
echo
yellow "[3/3] 等待服务就绪..."
for i in $(seq 1 30); do
  auth_ok=$(docker inspect supabase-auth-mini --format '{{.State.Health.Status}}' 2>/dev/null || echo "none")
  web_ok=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://localhost:3000/ 2>/dev/null || echo "000")
  if [ "$auth_ok" = "healthy" ] && [ "$web_ok" != "000" ]; then
    green "  就绪 (${i}0%)"
    break
  fi
  sleep 2
done

echo
echo "修复后的状态："
print_status

echo
green "完成。浏览器打开 http://localhost:3000 ，按 Ctrl+F5 强制刷新后再登录。"
yellow "如果登录仍然失败，看日志：docker logs --tail 50 supabase-auth-mini"
