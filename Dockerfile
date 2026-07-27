FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace
COPY pyproject.toml README.md ./
COPY src ./src
COPY prompts ./prompts
COPY config ./config

RUN python -m pip install --no-cache-dir .

ENTRYPOINT ["mathworkstation"]
