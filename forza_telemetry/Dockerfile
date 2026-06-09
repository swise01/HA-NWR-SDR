ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:2026.05.0
FROM ${BUILD_FROM}

RUN apk add --no-cache python3

COPY rootfs /
RUN chmod +x /run.sh /opt/forza_telemetry/forza_telemetry.py

CMD ["/run.sh"]

