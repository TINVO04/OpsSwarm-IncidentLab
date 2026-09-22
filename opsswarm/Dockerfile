FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY opsswarm ./opsswarm
COPY experiments ./experiments
COPY enterprise ./enterprise
COPY infrastructure ./infrastructure
RUN pip install --no-cache-dir .
EXPOSE 8080
CMD ["uvicorn","opsswarm.api:app","--host","0.0.0.0","--port","8080"]
