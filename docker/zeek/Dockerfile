# Build context is the repo root so we can reach blueflow/zeek/.
# See docker/docker-compose.yml: build.context = ".."
FROM zeek/zeek:latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 g++ iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY blueflow/zeek/scripts/ /scripts/
COPY blueflow/zeek/sidecar.py /app/sidecar.py
COPY docker/zeek/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN mkdir -p /work /logs /shared

ENTRYPOINT ["/entrypoint.sh"]
