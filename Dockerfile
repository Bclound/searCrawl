FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 crawler \
    && chmod -R a+rX /opt/browsers
COPY --chown=crawler:crawler . .
USER crawler
ENV API_HOST=0.0.0.0
EXPOSE 3000
CMD ["python", "main.py"]
