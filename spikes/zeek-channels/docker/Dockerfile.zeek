# Zeek container for the Stage 1 ZeekJS -> Redis Streams bridge.
#
# Base assumption: the official `zeek/zeek` image bundles the ZeekJS plugin
# (Zeek 6.0+, built with Node headers per
# https://docs.zeek.org/en/master/scripting/javascript.html).
# If `zeek --help | grep -i javascript` shows nothing after build, install
# the plugin explicitly with:
#   RUN zkg install --force zeekjs
# That requires zkg + Zeek headers in the base image.
FROM zeek/zeek:latest

# Node.js + npm so the bridge script can require('redis').
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm \
 && rm -rf /var/lib/apt/lists/*

# Install bridge dependencies at image-build time. The compose anonymous
# volume on /bridge/node_modules (see docker-compose.yml) preserves this
# tree when ./bridge is bind-mounted from the host for hot iteration.
WORKDIR /bridge
COPY bridge/package.json ./package.json
RUN npm install --omit=dev

# Bridge script itself is bind-mounted at runtime so edits don't need
# rebuilds. CMD is set in docker-compose.yml.
