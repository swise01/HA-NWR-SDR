ARG BUILD_FROM=ghcr.io/sdr-enthusiasts/docker-acarshub:latest
FROM ${BUILD_FROM}

ENV TZ=America/Chicago \
    ENABLE_ACARS=false \
    ENABLE_VDLM=true \
    VDLM_CONNECTIONS=udp \
    ENABLE_HFDL=false \
    ENABLE_IMSL=false \
    ENABLE_IRDM=false \
    ENABLE_ADSB=false \
    DB_SAVEALL=false \
    DB_SAVE_DAYS=14 \
    DB_ALERT_SAVE_DAYS=120 \
    MIN_LOG_LEVEL=3 \
    IATA_OVERRIDE="UP|UPS|United Parcel Service;US|AAL|American Airlines"

COPY rootfs /
RUN chmod +x /etc/cont-init.d/00-persist-acars-data

EXPOSE 80/tcp 5555/udp
