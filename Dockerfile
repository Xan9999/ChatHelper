FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 chathelper \
    && useradd --system --uid 10001 --gid chathelper --home-dir /nonexistent chathelper

COPY pyproject.toml README.md ./
COPY chathelper ./chathelper
RUN python -m pip install .

COPY --chown=chathelper:chathelper widget_styles ./widget_styles
COPY --chown=chathelper:chathelper widget_strings ./widget_strings

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "chathelper.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
