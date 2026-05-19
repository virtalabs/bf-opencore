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
    && apt-get install -y --no-install-recommends python3 libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

# Bundle the Zeek-side log policy and the Python sidecar. Both come from
# blueflow/zeek/ in the repo so the image stays in lockstep with whatever
# the source tree produces -- no separate "release" of the probe scripts.
COPY blueflow/zeek/scripts/arp_extract.zeek /opt/blueflow-zeek/scripts/arp_extract.zeek
COPY blueflow/zeek/sidecar.py /opt/blueflow-zeek/sidecar.py
COPY docker/zeek/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Drop root for the runtime. Zeek itself needs CAP_NET_RAW + CAP_NET_ADMIN
# for live capture on the host interface; we grant those via file caps on
# the zeek binary so the kernel re-applies them when entrypoint.sh execs
# zeek, regardless of the calling UID. The Python sidecar only makes HTTP
# PUTs (urllib) and needs no caps.
RUN groupadd --system zeekprobe \
    && useradd --system --gid zeekprobe --home-dir /var/log/zeek \
               --shell /usr/sbin/nologin zeekprobe \
    && setcap cap_net_raw,cap_net_admin+eip /usr/local/zeek/bin/zeek \
    && mkdir -p /var/log/zeek \
    && chown -R zeekprobe:zeekprobe /var/log/zeek /opt/blueflow-zeek

WORKDIR /var/log/zeek
USER zeekprobe

ENTRYPOINT ["/entrypoint.sh"]
