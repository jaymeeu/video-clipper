# 1) Build the static app with Node.
FROM node:24.14-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2) Serve it with Caddy (no Node at runtime): login + /api proxy, see Caddyfile.
FROM caddy:2.10.2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY --from=build /web/dist /srv
EXPOSE 80
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
