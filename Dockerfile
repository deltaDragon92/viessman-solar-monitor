FROM node:24-alpine AS web-builder

WORKDIR /app

COPY ui/package.json ui/package-lock.json ui/index.html ./
COPY ui/src ./src

RUN npm ci
RUN npm run build


FROM python:3.14-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SOLAR_API_HOST=0.0.0.0
ENV SOLAR_API_PORT=8765

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY --from=web-builder /app/dist ./ui/dist

EXPOSE 8765

CMD ["python3", "backend/solar_api_server.py", "--host", "0.0.0.0", "--port", "8765"]
