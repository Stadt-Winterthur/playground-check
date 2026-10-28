FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN groupadd --system --gid 10001 playground \
    && useradd --system --uid 10001 --gid playground --home-dir /app playground

COPY --chown=playground:playground . /app
RUN pip install --no-cache-dir ".[production,django]" \
    && chown -R playground:playground /app

USER playground

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/health', timeout=2)" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8010", "--workers", "1", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "playground_check.django_project.wsgi:application"]
