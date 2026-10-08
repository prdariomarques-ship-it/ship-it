FROM node:20-alpine AS deps
WORKDIR /app
# package-lock.json copiado e `npm ci` (não `npm install`) — build
# reproduzível: a mesma árvore de dependências toda vez, não a mais
# recente que satisfizer os ranges do package.json no dia do build.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# public/ (inclui sw.js, o service worker, e o favicon) não é copiado
# automaticamente para o output standalone pelo Next — sem esta linha a
# imagem sobe sem esses assets, 404 em produção. Achado numa revisão de
# código, confirmado reproduzindo o build standalone localmente.
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
