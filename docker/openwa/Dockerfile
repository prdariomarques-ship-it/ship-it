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

# lib/wapi.js's getStore() IIFE resolves window.Store by requiring
# WhatsApp's own internal "WAWebCollections" module, then — only when
# window.Store.Chat came back non-null — overrides
# Store.Chat.modelClass.prototype.sendMessage to delegate to
# window.Store.SendTextMsgToChat(this, ...arguments), a second WhatsApp
# internal function resolved the same way.
#
# Root cause, confirmed with runtime evidence (not assumed): WhatsApp's
# module system loads WAWebCollections' ~45 dependency collections
# (WAWebChatCollection, WAWebContactCollection, WAWebMsgCollection, etc.)
# asynchronously; open-wa's require() call races against that and isn't
# guaranteed to see a populated Store.Chat. When the race resolves in
# open-wa's favor and the override installs, chat.sendMessage() reaches
# Store.SendTextMsgToChat, which throws "t.isRegularUser is not a
# function" for every recipient — reproduced directly against a live,
# paired WhatsApp Business account. isRegularUser is a genuine, current
# method (confirmed by fetching WhatsApp's own served bundle directly:
# `n.isRegularUser=function(){return this.isUser()&&!this.isPSA()&&!this.isBot()}`,
# 17 occurrences, tied throughout to WAWebLidMigrationUtils) — it exists
# on WhatsApp's newer Wid (LID-aware identifier) class, but whatever
# object Store.SendTextMsgToChat ends up operating on isn't one. This is
# WhatsApp's LID (Linked ID) migration, an ongoing architecture change
# also breaking other, unrelated WhatsApp Web automation libraries
# (whatsapp-web.js hit the same class of failure, "Lid is missing in
# chat table", fixed in their v1.33.3) and already tracked, unresolved,
# against open-wa itself (github.com/open-wa/wa-automate-nodejs/issues/3322,
# opened 2026-02-23, still open; no LID-related fix exists anywhere in
# wapi.js's commit history — its last substantive change predates
# WhatsApp's LID rollout).
#
# When the require() race instead resolves against open-wa (Store.Chat
# not yet populated), the override never installs and chat.sendMessage
# stays WhatsApp's own native implementation — which is already correctly
# LID-aware, since it's WhatsApp's current code. Verified directly: a
# real sendText call in that state succeeded, its response id containing
# "@lid".
#
# Retrying/waiting for Store.Chat to become available, so the override
# installs more reliably, would therefore make sending *more* consistently
# broken, not less — the override is what's incompatible with LID, not a
# timing problem to smooth over. The fix is the opposite: never let
# open-wa install this specific override by default, so every send goes
# through WhatsApp's own native, LID-aware sendMessage.
#
# Implemented as a runtime feature flag rather than deleting the override
# outright, gated on WA_ENABLE_LEGACY_SENDMESSAGE_OVERRIDE (unset/anything
# but "true" = disabled = current default; "true" = restores stock
# open-wa behavior). wapi.js itself is left untouched — it's injected into
# the browser as a raw string (page.evaluate), where process.env doesn't
# exist, so the flag can't be read from inside it. Patched instead at
# controllers/script_preloader.js's getScript(), the one place on the
# Node side that reads wapi.js off disk (and caches it for the process's
# lifetime — every later "Reinjecting api" cycle reuses this same
# already-flag-applied string, it doesn't re-read the file), stripping the
# override from the cached content unless the flag is explicitly on.
RUN node -e "\
const fs = require('fs'); \
const p = '/usr/src/app/node_modules/@open-wa/wa-automate/dist/controllers/script_preloader.js'; \
const src = fs.readFileSync(p, 'utf8'); \
const needle = 'this.contentRegistry[scriptName] = yield read(scriptName);'; \
if (!src.includes(needle)) { console.error('PATCH TARGET NOT FOUND — script_preloader.js changed upstream, needs re-verification'); process.exit(1); } \
const replacement = 'this.contentRegistry[scriptName] = yield read(scriptName); ' + \
    'if (scriptName === ' + JSON.stringify('wapi.js') + ' && process.env.WA_ENABLE_LEGACY_SENDMESSAGE_OVERRIDE !== ' + JSON.stringify('true') + ') { ' + \
    'const before = this.contentRegistry[scriptName]; ' + \
    'const needle2 = ' + JSON.stringify('if (window.Store.Chat) window.Store.Chat.modelClass.prototype.sendMessage = function (e) {\n                window.Store.SendTextMsgToChat(this, ...arguments);\n            }') + '; ' + \
    'if (before.includes(needle2)) { this.contentRegistry[scriptName] = before.replace(needle2, ' + JSON.stringify('/* LID incompatibility — see docker/openwa/Dockerfile — override disabled by default, set WA_ENABLE_LEGACY_SENDMESSAGE_OVERRIDE=true to restore it */') + '); console.log(' + JSON.stringify('[LID patch] sendMessage override stripped from wapi.js (WA_ENABLE_LEGACY_SENDMESSAGE_OVERRIDE not set to true)') + '); } ' + \
    'else { console.log(' + JSON.stringify('[LID patch] override pattern not found in wapi.js at runtime — leaving content as-is (nothing to strip, or upstream changed)') + '); } ' + \
    '} '; \
fs.writeFileSync(p, src.replace(needle, replacement)); \
console.log('script_preloader.js patched OK'); \
" \
    && node -c /usr/src/app/node_modules/@open-wa/wa-automate/dist/controllers/script_preloader.js

USER owauser
