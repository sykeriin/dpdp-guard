FROM node:22-slim
WORKDIR /app
COPY dashboard/package*.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard .
ARG NEXT_PUBLIC_GUARD_URL=http://localhost:8000
ENV NEXT_PUBLIC_GUARD_URL=$NEXT_PUBLIC_GUARD_URL
RUN npx next build
CMD ["npx","next","start","-p","3000"]
