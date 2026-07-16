# openwa/wa-automate:latest is Debian-based but ships without procps.
# @open-wa/wa-automate's own transitive dependency `ps-tree` shells out to
# `ps -A -o ppid,pid,stat,comm` to find and clean up orphaned Chromium
# processes after a page-ready timeout, and never attaches an `error`
# listener to that child process — so a missing `ps` binary (ENOENT) is an
# uncaught exception that kills the whole Node process, producing an
# infinite restart loop before a QR code ever has a chance to be scanned.
FROM openwa/wa-automate:latest
USER root
# The base image's own Google Chrome apt repo has an expired/rotated signing
# key, which makes `apt-get update` fail outright. Chrome itself is already
# installed and isn't being touched here, so the repo definition is removed
# rather than re-trusted, to install procps from the standard Debian repos.
RUN rm -f /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

# The library unconditionally overrides the page's user agent via CDP
# (Network.setUserAgentOverride) with a hardcoded, stale string claiming
# Chrome/104 (config/puppeteer.config.js) when no customUserAgent is
# configured. Confirmed by direct reproduction: WhatsApp Web serves its
# "update your browser" gate — a static page, so window.Debug never
# appears and the QR code never loads — whenever setUserAgent() is called
# at all, independent of the value passed (tested the stale default, the
# real installed Chrome's own current UA string, and that UA plus matching
# userAgentMetadata/Client Hints — all three still got the gate). Only
# skipping the override entirely (leaving the browser's own real,
# internally-consistent UA and Client Hints untouched) reproducibly reached
# the actual QR page. Patched to only call setUserAgent() when a
# customUserAgent is explicitly configured, instead of always falling back
# to the broken default.
RUN sed -i \
    's#setupPromises.push(waPage.setUserAgent(customUserAgent || puppeteer_config_1.useragent));#if (customUserAgent) { setupPromises.push(waPage.setUserAgent(customUserAgent)); }#' \
    /usr/src/app/node_modules/@open-wa/wa-automate/dist/controllers/browser.js \
    && grep -q "if (customUserAgent) { setupPromises.push" /usr/src/app/node_modules/@open-wa/wa-automate/dist/controllers/browser.js

# The QR auth page (controllers/popup/index.html, served at :8002) logs
# every socket message's raw `.data` into the on-page `.log` panel, and
# only excludes the "sessionDataBase64" namespace from that dump — not
# "qr", whose `.data` is the QR code's own full base64 data: URI. The
# image itself renders fine via a separate, correct `.src = message.data`
# assignment a few lines above; this second, unconditional block just
# additionally dumps that same giant base64 string as visible text into
# the log panel. Excluded "qr" the same way "sessionDataBase64" already is.
RUN sed -i \
    's#if (message.namespace !== "sessionDataBase64") $(#if (message.namespace !== "sessionDataBase64" \&\& message.namespace !== "qr") $(#' \
    /usr/src/app/node_modules/@open-wa/wa-automate/dist/controllers/popup/index.html \
    && grep -q 'message.namespace !== "sessionDataBase64" && message.namespace !== "qr"' /usr/src/app/node_modules/@open-wa/wa-automate/dist/controllers/popup/index.html

USER owauser
