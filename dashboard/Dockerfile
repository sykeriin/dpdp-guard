FROM node:22-slim
WORKDIR /app
COPY dashboard/package*.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard .
RUN npx next build
CMD ["npx","next","start","-p","3000"]
