# Multi-stage build: the builder stage compiles/installs everything into a
# self-contained venv; the runtime stage copies only that venv plus the app
# code. Build tools, pip caches, and layer history with source churn never
# reach the final image — smaller attack surface and smaller pulls.

FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps .


FROM python:3.12-slim

# Never run an internet-facing process as root: if an attacker gets code
# execution through the app, they land as an unprivileged user inside the
# container instead of root (which makes container-escape bugs exploitable).
RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
WORKDIR /home/appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "--factory", "truthlayer.api:create_app", "--host", "0.0.0.0", "--port", "8000"]
