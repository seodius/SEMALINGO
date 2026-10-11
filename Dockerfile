FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install the package first so this layer is cached until the code changes.
COPY pyproject.toml README.md LICENSE ./
COPY semalingo ./semalingo
RUN pip install --no-cache-dir ".[mcp]"

# The registry and the reviewed mappings are read from the working directory.
COPY sources.yaml DATA-LICENSES.md ./
COPY mappings ./mappings

RUN useradd --create-home --uid 1000 semalingo \
    && mkdir -p /app/data \
    && chown semalingo /app/data
USER semalingo

# Raw downloads and the DuckDB database live here; mount a host folder or a volume.
VOLUME ["/app/data"]

ENTRYPOINT ["semalingo"]
CMD ["--help"]
