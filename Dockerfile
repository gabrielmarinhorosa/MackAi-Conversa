FROM node:22-slim AS front
WORKDIR /front
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Endereços do Módulo 1 que o navegador chama. Vazios = endereços publicados do Módulo 1.
ARG VITE_MOD1_AUTH_URL=""
ARG VITE_MOD1_PROJECTS_URL=""
ARG VITE_MOD1_FRONTEND_URL=""
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY assistente_conversacional/ assistente_conversacional/
COPY --from=front /front/dist frontend_dist/
EXPOSE 8000
CMD ["uvicorn", "assistente_conversacional.main:app", "--host", "0.0.0.0", "--port", "8000"]
