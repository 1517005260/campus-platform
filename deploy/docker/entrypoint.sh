#!/bin/sh
# 同一个镜像按角色启动：api | worker | beat | consumer | migrate | mq-setup
set -e

case "$1" in
  api)
    # 迁移（回滚时数据库比镜像新则跳过）与种子数据都可重复执行；worker/beat 等 api 就绪后才启动。
    # 服务只在 Docker 内网可达，唯一入口是网关，因此信任内网转发的 X-Forwarded-For 以记录真实客户端地址
    python -m campus_common.migrate
    python -m app.seed
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" \
      --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
    ;;
  worker)
    exec celery -A app.worker worker --loglevel=INFO --concurrency="${WORKER_CONCURRENCY:-2}" \
      --hostname "${CELERY_HOSTNAME:-worker}@%h"
    ;;
  beat)
    # 每个环境每个服务只能运行一个 beat
    exec celery -A app.worker beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule
    ;;
  consumer)
    # ASGI 方式运行消费者，/health 供容器健康检查
    exec uvicorn app.consumers:app --host 0.0.0.0 --port "${CONSUMER_PORT:-8090}"
    ;;
  migrate)
    exec python -m campus_common.migrate
    ;;
  mq-setup)
    # 一次性任务：以管理员账号声明消息拓扑、设置 policy、创建业务账号
    exec python -m campus_common.mqctl setup
    ;;
  *)
    exec "$@"
    ;;
esac
