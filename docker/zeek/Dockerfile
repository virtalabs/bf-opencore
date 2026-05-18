# Standalone Zeek probe for BlueFlow asset discovery.
#
# Bundles Zeek + the arp_extract.zeek log policy + the conn+arp sidecar
# into a single long-running image. The container expects to be told
# (via env) which interface to listen on and which BlueFlow to push to.
#
# Build context MUST be the repo root so the COPY steps below can reach
# blueflow/zeek/. Build from the repo root:
#
#   docker build -f docker/zeek/Dockerfile -t virtalabsinc/zeek-probe:latest .

FROM zeek/zeek:latest

LABEL org.opencontainers.image.title="zeek-probe" \
      org.opencontainers.image.description="Long-running Zeek probe that ships conn + ARP observations to a BlueFlow API." \
      org.opencontainers.image.source="https://github.com/virtalabs/blueflow" \
      org.opencontainers.image.vendor="Virta Laboratories, Inc."

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

# Bundle the Zeek-side log policy and the Python sidecar. Both come from
# blueflow/zeek/ in the repo so the image stays in lockstep with whatever
# the source tree produces -- no separate "release" of the probe scripts.
COPY blueflow/zeek/scripts/arp_extract.zeek /opt/blueflow-zeek/scripts/arp_extract.zeek
COPY blueflow/zeek/sidecar.py /opt/blueflow-zeek/sidecar.py
COPY docker/zeek/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Zeek writes its logs into CWD. Use a dedicated dir so the layout is
# predictable for the entrypoint loop and for anyone exec-ing into the
# container to debug.
RUN mkdir -p /var/log/zeek
WORKDIR /var/log/zeek

ENTRYPOINT ["/entrypoint.sh"]
