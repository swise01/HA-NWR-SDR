ARG BUILD_FROM=ghcr.io/sdr-enthusiasts/acars_router:latest
FROM ${BUILD_FROM}

ENV TZ=America/Chicago \
    AR_VERBOSITY=info \
    AR_ENABLE_DEDUPE=true \
    AR_OVERRIDE_STATION_NAME=SW-KBHM-VDL \
    AR_LISTEN_UDP_VDLM2=5555 \
    AR_SEND_UDP_VDLM2=local-acarshub:5555 \
    AR_SEND_TCP_VDLM2=feed.airframes.io:5553 \
    AR_DISABLE_ACARS=true \
    AR_DISABLE_HFDL=true \
    AR_DISABLE_IMSL=true \
    AR_DISABLE_IRDM=true

EXPOSE 5555/udp
