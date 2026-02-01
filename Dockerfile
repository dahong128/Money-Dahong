FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd -m -u 10001 appuser \
  && chown -R appuser:appuser /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
COPY configs /app/configs

RUN python -m pip install --no-cache-dir --upgrade pip \
  && python -m pip install --no-cache-dir .

USER appuser

ENTRYPOINT ["money-dahong"]
CMD ["run"]
