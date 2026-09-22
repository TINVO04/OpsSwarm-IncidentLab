FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY opsswarm ./opsswarm
COPY experiments ./experiments
COPY enterprise ./enterprise
COPY infrastructure ./infrastructure
COPY config ./config
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "httpx>=0.27,<1" "pydantic>=2.8,<3" "pydantic-settings>=2.4,<3" "PyYAML>=6.0,<7" "requests>=2.32,<3"
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["uvicorn","opsswarm.api:app","--host","0.0.0.0","--port","8080"]
