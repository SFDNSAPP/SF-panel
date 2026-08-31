# ═══════════════ SF-Panel — Dockerfile ═══════════════
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SF_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl unzip openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY core/ core/
COPY api/ api/
COPY telegram/ telegram/
COPY web/ web/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# ---- هسته Xray را موقع build دانلود می‌کنیم تا استارت سریع باشد ----
RUN case "$(dpkg --print-architecture)" in \
        arm64) ASSET=Xray-linux-arm64-v8a.zip ;; \
        *)     ASSET=Xray-linux-64.zip ;; \
    esac && \
    curl -fsSL -o /tmp/x.zip \
        "https://github.com/XTLS/Xray-core/releases/latest/download/$ASSET" && \
    unzip -o /tmp/x.zip xray geoip.dat geosite.dat -d /opt/xray && \
    rm /tmp/x.zip && chmod +x /opt/xray/xray

VOLUME ["/data"]
ENTRYPOINT ["./docker-entrypoint.sh"]