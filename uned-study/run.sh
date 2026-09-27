#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting UNED Study"
exec python3 -m uned_study.server
