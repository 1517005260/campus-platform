# 常用命令。服务名取 common / m1-seat / m2-room / m3-repair。

PORT_common    := 8004
PORT_m1-seat   := 8001
PORT_m2-room   := 8002
PORT_m3-repair := 8003

# 各服务的数据库角色（开发与测试库中密码同角色名）
ROLE_common    := common_svc
ROLE_m1-seat   := m1_seat
ROLE_m2-room   := m2_room
ROLE_m3-repair := m3_repair

# 本机进程监听地址。开发网关在容器内经 host.docker.internal 访问它们：Docker Desktop / OrbStack
# 可访问宿主机回环地址；Linux 原生 Docker 需设为 0.0.0.0（make run svc=... DEV_BIND_HOST=0.0.0.0）
DEV_BIND_HOST ?= 127.0.0.1

# 开发 RabbitMQ 的管理员账号（只用于 mqctl setup）；服务进程与部署环境一样使用受限的业务账号 campus_app
DEV_MQ_ADMIN_URL := amqp://campus:campus@localhost:5672//

# 测试只连 *_test 库（公共库的 pytest 插件会拒绝其他库），并且与部署环境一样使用本服务自己的角色
TEST_DATABASE_URL ?= postgresql+psycopg://$(ROLE_$(svc)):$(ROLE_$(svc))@localhost:5432/campus_test

.PHONY: setup deps deps-down test-db mq-setup run worker beat consumer test lint fmt contracts migration fe mq-status

setup:            ## 安装全部依赖（首次克隆后执行一次）
	uv sync --all-packages
	cd frontend && npm ci

deps:             ## 启动 Postgres / Redis / RabbitMQ / Mailpit / 开发网关
	docker compose -f deploy/docker-compose.dev.yml up -d

test-db:          ## 确保测试库 campus_test 存在（可重复执行；开发 Postgres 首次初始化时也会自动创建）
	docker compose -f deploy/docker-compose.dev.yml exec -T postgres bash < deploy/postgres/test-db.sh

deps-down:
	docker compose -f deploy/docker-compose.dev.yml down

fe:               ## 运行前端开发服务器（3000）
	cd frontend && npm run dev -- --host $(DEV_BIND_HOST)

# 与部署环境的 mq-setup 容器相同：声明消息拓扑与 policy、创建业务账号。可重复执行，
# 下面所有连接 RabbitMQ 的进程启动前都会先执行它，新机器上任何一个进程都可以单独启动
mq-setup:         ## 声明消息拓扑并创建业务账号 campus_app（run / worker / beat / consumer 会自动执行）
	RABBITMQ_URL=$(DEV_MQ_ADMIN_URL) RABBITMQ_APP_USER=campus_app RABBITMQ_APP_PASSWORD=campus_app \
		uv run --no-sync python -m campus_common.mqctl setup

run: mq-setup     ## 本地运行某个服务（含迁移和演示种子）：make run svc=m1-seat
	cd services/$(svc) && uv run --no-sync python -m campus_common.migrate && SEED_DEMO=true uv run --no-sync python -m app.seed \
		&& uv run --no-sync uvicorn app.main:app --reload --host $(DEV_BIND_HOST) --port $(PORT_$(svc))

worker: mq-setup  ## 本地运行某个服务的 Celery worker：make worker svc=m1-seat
	cd services/$(svc) && uv run --no-sync celery -A app.worker worker --loglevel=INFO --hostname "$(svc)@%h"

beat: mq-setup    ## 本地运行某个服务的 Celery beat：make beat svc=m1-seat
	cd services/$(svc) && uv run --no-sync celery -A app.worker beat --loglevel=INFO --schedule=/tmp/celerybeat-$(svc)

consumer: mq-setup ## 本地运行 common 的消息消费者（/health 在 8090）
	cd services/common && uv run --no-sync uvicorn app.consumers:app --port 8090

test:             ## 运行某个服务的测试（连接 campus_test）：make test svc=m1-seat [ARGS="tests/test_jobs.py -k deadline"]
	cd services/$(svc) && DATABASE_URL=$(TEST_DATABASE_URL) uv run --no-sync pytest --cov=app $(ARGS)

mq-status:        ## 查看消息队列积压、重试中、死信与未路由消息数
	uv run --no-sync python -m campus_common.mqctl status

lint:
	uv run --no-sync ruff check . && uv run --no-sync ruff format --check .

fmt:
	uv run --no-sync ruff check --fix . && uv run --no-sync ruff format .

contracts:        ## 改了接口或消息模型后重新生成契约快照和前端类型
	scripts/update_contracts.sh
	cd frontend && npm run gen:types

migration:        ## 生成迁移：make migration svc=m1-seat rev=0002 msg="add seat tags"
	cd services/$(svc) && uv run --no-sync alembic revision --autogenerate --rev-id $(rev) -m "$(msg)"
