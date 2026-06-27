FROM python:3.12-slim

ARG BW_VERSION=2026.6.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -ex \
    && case "$(uname -m)" in \
        aarch64) BW_ARCH="-arm64" ;; \
        *)       BW_ARCH="" ;; \
    esac \
    && curl -fsSL "https://github.com/bitwarden/clients/releases/download/cli-v${BW_VERSION}/bw-linux${BW_ARCH}-${BW_VERSION}.zip" \
        -o /tmp/bw.zip \
    && unzip /tmp/bw.zip -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/bw \
    && rm /tmp/bw.zip

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync.py .
COPY src/ src/

RUN mkdir -p /data

HEALTHCHECK --interval=1h --timeout=10s --start-period=5m \
    CMD test -f /data/last_sync || exit 1

CMD ["python", "sync.py"]
