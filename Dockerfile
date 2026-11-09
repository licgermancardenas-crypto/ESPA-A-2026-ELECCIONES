FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gdal-bin && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY dbt ./dbt
RUN pip install --no-cache-dir -e ".[dev]"
ENV ATLAS_ROOT=/app ATLAS_DATA=/app/data
EXPOSE 8000
CMD ["uvicorn", "atlas_spain.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
