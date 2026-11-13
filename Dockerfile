FROM ghcr.io/astral-sh/uv:python3.12-bookworm

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project
COPY blazer_drive ./blazer_drive
COPY tests ./tests
COPY translations ./translations

ENV PATH="/app/.venv/bin:${PATH}"
ENTRYPOINT ["python", "-m", "blazer_drive"]
CMD ["--help"]
