FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000

# Dev-only image: runs as root and bind-mounts ./frontend over /app (see docker-compose.yml) with
# `npm run dev`'s hot-reload watching the filesystem - see Dockerfile.prod for the multi-stage,
# non-root, `next build`+`next start` production image instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["npm", "run", "dev"]