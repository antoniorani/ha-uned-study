FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="UNED Study" \
  org.opencontainers.image.source="https://github.com/antoniorani/ha-uned-study"

RUN apk add --no-cache \
    python3 \
    py3-aiohttp \
    ca-certificates

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /app
CMD ["/run.sh"]
