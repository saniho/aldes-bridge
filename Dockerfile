# stage 1 : build du frontend React
FROM node:20-alpine AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ .
RUN npm run build

# stage 2 : runtime python
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV ALDES_WEB_DIR=/app/dist
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./server/
COPY profiles/ ./profiles/
COPY --from=web /app/web/dist ./dist
EXPOSE 8883 8080
ENTRYPOINT ["python3", "-m", "server.main"]