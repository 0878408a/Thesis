# ============================================================================
# Customer Frontend production image (multi-stage)
# Build context: thesis/customer_agent/frontend/customer
#
# 兩階段: 1) node build (vite production)  2) nginx serve static
# - 最終 image 不含 node_modules
# - 不帶任何 secret; .env / 憑證一律 volume 注入
# - nginx 對外路由由 compose 掛 /etc/nginx/conf.d 的 customer 專用 conf
# ============================================================================

# ---------- Stage 1: build ----------
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- Stage 2: serve (nginx static) ----------
FROM nginx:1.27-alpine
# 把 build 產出放進 nginx 靜態目錄
COPY --from=build /app/dist /usr/share/nginx/html
# 容器不 bake 自訂 nginx.conf; 由 compose 以 volume 掛入 customer 端路由設定
# (nginx 預設 main.conf include /etc/nginx/conf.d/*.conf, compose 掛一份 customer.conf)
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
