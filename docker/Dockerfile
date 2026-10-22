# Pin base image to a specific digest for reproducible builds.
# To update: re-run the "Build Docker Base Image" workflow, then run
#   docker buildx imagetools inspect ghcr.io/jtn0123/compresso-base:latest
# and replace the digest below with the new value.
ARG BASE_IMAGE=ghcr.io/jtn0123/compresso-base@sha256:1a2bc1fe70a66160fb9146a071ad4f2862fe1c651d601170bdc95aeba6a4725a
FROM ${BASE_IMAGE}

# Patch OS packages that have security fixes newer than the pinned base image.
# Drop entries here once the base image is rebuilt with the fix included.
RUN \
    echo "**** Patch linux-libc-dev CVE-2026-43185 (fixed in 6.8.0-134.134) ****" \
        && echo "**** Patch libssl3t64/openssl CVE-2026-84782 (fixed in 3.0.13-0ubuntu3.16) ****" \
        && apt-get update \
        && apt-get install -y --only-upgrade linux-libc-dev libssl3t64 openssl \
        && apt-get clean autoclean -y \
        && apt-get autoremove -y \
        && rm -rf /var/lib/apt/lists/*

# Install pre-built Compresso wheel
COPY /dist/ /src/
RUN \
    echo "**** Install Compresso ****" \
        && WHEEL_PATH="$(ls -1 /src/*.whl | sort | tail -n 1)" \
        && echo "Installing ${WHEEL_PATH}" \
        && "${VIRTUAL_ENV:?}"/bin/pip install --no-cache-dir "${WHEEL_PATH}" \
    && \
    echo "**** Upgrade venv pip (vendored certifi GHSA-6q48-6c7w-9gw2) ****" \
        && echo "pip==26.2.2 --hash=sha256:fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70" > /tmp/pip.req \
        && "${VIRTUAL_ENV:?}"/bin/pip install --no-cache-dir --require-hashes -r /tmp/pip.req \
        && rm -f /tmp/pip.req \
    && \
    echo "**** Patch picomatch CVE-2026-33671 in bundled npm ****" \
        && PICO_DIR="/usr/lib/node_modules/npm/node_modules/tinyglobby/node_modules/picomatch" \
        && if [ -d "$PICO_DIR" ]; then \
            cd "$PICO_DIR" \
            && npm pack picomatch@4.0.4 2>/dev/null \
            && tar -xzf picomatch-*.tgz --strip-components=1 \
            && rm -f picomatch-*.tgz \
            && cd /; \
        fi \
    && \
    echo "**** Patch sigstore CVE-2026-48815 in bundled npm ****" \
        && SIGSTORE_DIR="/usr/lib/node_modules/npm/node_modules/sigstore" \
        && if [ -d "$SIGSTORE_DIR" ]; then \
            cd "$SIGSTORE_DIR" \
            && npm pack sigstore@4.1.1 2>/dev/null \
            && tar -xzf sigstore-*.tgz --strip-components=1 \
            && rm -f sigstore-*.tgz \
            && cd /; \
        fi \
    && \
    echo "**** Patch ip-address CVE-2026-69192 in bundled npm ****" \
        && IPADDR_DIR="/usr/lib/node_modules/npm/node_modules/ip-address" \
        && if [ -d "$IPADDR_DIR" ]; then \
            cd "$IPADDR_DIR" \
            && npm pack ip-address@10.3.1 2>/dev/null \
            && tar -xzf ip-address-*.tgz --strip-components=1 \
            && rm -f ip-address-*.tgz \
            && cd /; \
        fi \
    && \
    echo "**** Patch tar CVE-2026-73566 in bundled npm ****" \
        && TAR_DIR="/usr/lib/node_modules/npm/node_modules/tar" \
        && if [ -d "$TAR_DIR" ]; then \
            cd "$TAR_DIR" \
            && npm pack tar@7.5.22 2>/dev/null \
            && tar -xzf tar-*.tgz --strip-components=1 \
            && rm -f tar-*.tgz \
            && cd /; \
        fi \
    && \
    echo "**** Patch brace-expansion CVE-2026-102276/102278/14257/69152 in bundled npm ****" \
        && BRACE_DIR="/usr/lib/node_modules/npm/node_modules/brace-expansion" \
        && if [ -d "$BRACE_DIR" ]; then \
            cd "$BRACE_DIR" \
            && npm pack brace-expansion@5.0.12 2>/dev/null \
            && tar -xzf brace-expansion-*.tgz --strip-components=1 \
            && rm -f brace-expansion-*.tgz \
            && cd /; \
        fi \
    && \
    echo "**** Patch undici CVE-2026-19534 in bundled npm ****" \
        && UNDICI_DIR="/usr/lib/node_modules/npm/node_modules/undici" \
        && if [ -d "$UNDICI_DIR" ]; then \
            cd "$UNDICI_DIR" \
            && npm pack undici@6.29.1 2>/dev/null \
            && tar -xzf undici-*.tgz --strip-components=1 \
            && rm -f undici-*.tgz \
            && cd /; \
        fi \
    && \
    echo "**** Patch pacote CVE-2026-9496 in bundled npm (last: npm pack needs pacote) ****" \
        && PACOTE_DIR="/usr/lib/node_modules/npm/node_modules/pacote" \
        && if [ -d "$PACOTE_DIR" ]; then \
            cd "$PACOTE_DIR" \
            && npm pack pacote@21.5.1 2>/dev/null \
            && tar -xzf pacote-*.tgz --strip-components=1 \
            && rm -f pacote-*.tgz \
            && cd /; \
        fi \
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
