# 构建上下文是仓库根目录：docker build -f services/m1-seat/Dockerfile .
FROM python:3.12.15-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /repo

# 依赖层：只拷贝锁文件和各成员的 pyproject.toml，业务代码改动不会触发依赖重装
COPY pyproject.toml uv.lock ./
COPY libs/campus_common/pyproject.toml libs/campus_common/
COPY services/common/pyproject.toml services/common/
COPY services/m1-seat/pyproject.toml services/m1-seat/
COPY services/m2-room/pyproject.toml services/m2-room/
COPY services/m3-repair/pyproject.toml services/m3-repair/
RUN uv sync --frozen --no-dev --package m1-seat --no-install-workspace

COPY libs/campus_common libs/campus_common
RUN uv sync --frozen --no-dev --package m1-seat --no-editable

WORKDIR /repo/services/m1-seat
COPY services/m1-seat/ ./
COPY deploy/docker/entrypoint.sh /entrypoint.sh

# 以非 root 用户运行；代码与依赖属于 root，运行时只读
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app

ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ENV APP_VERSION=$APP_VERSION GIT_SHA=$GIT_SHA PORT=8001

EXPOSE 8001
ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
