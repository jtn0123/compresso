ARG BASE_IMAGE=ghcr.io/jtn0123/compresso-base:latest
FROM ${BASE_IMAGE}

# Install pre-built Compresso wheel
COPY /dist/ /src/
RUN \
    echo "**** Install Compresso ****" \
        && WHEEL_PATH="$(ls -1 /src/*.whl | sort | tail -n 1)" \
        && echo "Installing ${WHEEL_PATH}" \
        && "${VIRTUAL_ENV:?}"/bin/pip install --no-cache-dir "${WHEEL_PATH}" \
        && \
        echo "**** Make default paths for compresso library ****" \
            && mkdir -p /library


# Add local files
COPY /docker/root /

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/bin/compresso"]

# Health check using the readiness endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsSL http://127.0.0.1:8888/compresso/api/v2/healthcheck/readiness || exit 1

# Compresso runs on port 8888
EXPOSE 8888/tcp
