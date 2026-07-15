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
USER owauser
