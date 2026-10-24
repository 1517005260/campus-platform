# 构建上下文是 frontend 目录：docker build -t campus-frontend frontend
FROM node:22.23.3-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION
# 类型已从 contracts/ 生成并提交到 src/api/types，构建时不需要 contracts 目录
RUN npm run build

# 非 root 的 nginx 镜像，监听 8080
FROM nginxinc/nginx-unprivileged:1.27.5-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
