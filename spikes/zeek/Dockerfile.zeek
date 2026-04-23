FROM zeek/zeek:latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 g++ iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/ /scripts/
COPY sidecar.py /app/sidecar.py
COPY entrypoint-zeek.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN mkdir -p /work /logs /shared

ENTRYPOINT ["/entrypoint.sh"]
