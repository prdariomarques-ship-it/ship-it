/**
 * Service Worker for Frontend Optimization (OBS-003)
 *
 * Implements:
 * - Static asset caching (CSS, JS, images) — 30-day cache
 * - Network-first for API calls (fallback to cache)
 * - Cache versioning for invalidation
 * - Offline functionality
 */

const CACHE_VERSION = "v1.0.0";
const ASSET_CACHE = `assets-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;
const CACHE_URLS = [
  "/",
  "/index.html",
  "/favicon.ico",
  "/manifest.json",
];

// Cache strategies
const CACHE_STRATEGIES = {
  CACHE_FIRST: "cache_first", // Assets: check cache first, fall back to network
  NETWORK_FIRST: "network_first", // API: check network first, fall back to cache
  STALE_WHILE_REVALIDATE: "stale_while_revalidate", // Return cached, update in background
};

/**
 * Install event - cache essential assets
 */
self.addEventListener("install", (event) => {
  console.log("[SW] Installing service worker", CACHE_VERSION);

  event.waitUntil(
    caches.open(ASSET_CACHE).then((cache) => {
      console.log("[SW] Caching essential assets");
      return cache.addAll(CACHE_URLS).catch((error) => {
        console.warn("[SW] Failed to cache essential assets:", error);
        // Don't fail install if some assets can't be cached
        return Promise.resolve();
      });
    })
  );

  // Force activation
  self.skipWaiting();
});

/**
 * Activate event - clean up old caches
 */
self.addEventListener("activate", (event) => {
  console.log("[SW] Activating service worker");

  event.waitUntil(
    caches.keys().then((cacheNames) => {
      const currentCaches = [ASSET_CACHE, API_CACHE];
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (!currentCaches.includes(cacheName)) {
            console.log("[SW] Deleting old cache:", cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );

  self.clients.claim();
});

/**
 * Fetch event - implement caching strategies
 */
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== "GET") {
    return;
  }

  // Determine strategy based on request type
  if (isAPIRequest(url)) {
    // Network-first for API
    event.respondWith(networkFirstStrategy(request));
  } else {
    // Cache-first for assets
    event.respondWith(cacheFirstStrategy(request));
  }
});

/**
 * Check if request is API call
 */
function isAPIRequest(url) {
  return url.pathname.startsWith("/api/");
}

/**
 * Cache-first strategy for static assets
 * 1. Check cache
 * 2. If miss, fetch from network
 * 3. Cache response for future use
 */
async function cacheFirstStrategy(request) {
  try {
    // Check cache
    const cached = await caches.match(request);
    if (cached) {
      console.log("[SW] Cache hit:", request.url);
      return cached;
    }

    // Fetch from network
    console.log("[SW] Cache miss, fetching:", request.url);
    const response = await fetch(request);

    // Cache successful responses
    if (response.ok) {
      const cache = await caches.open(ASSET_CACHE);
      cache.put(request, response.clone());
    }

    return response;
  } catch (error) {
    console.warn("[SW] Fetch failed:", request.url, error);

    // Return cached fallback or offline page
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    return new Response("Offline - no cached content available", {
      status: 503,
      statusText: "Service Unavailable",
    });
  }
}

/**
 * Network-first strategy for API calls
 * 1. Try network
 * 2. If fails, return cached response
 * 3. Cache successful responses for future use
 */
async function networkFirstStrategy(request) {
  try {
    // Try network first
    const response = await fetch(request);

    // Cache successful responses
    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }

    console.log("[SW] Network response:", request.url, response.status);
    return response;
  } catch (error) {
    console.warn("[SW] Network failed for API call:", request.url, error);

    // Fall back to cache
    const cached = await caches.match(request);
    if (cached) {
      console.log("[SW] Using cached API response:", request.url);
      return cached;
    }

    // Return error response
    return new Response(
      JSON.stringify({
        error: "Network error and no cached response available",
      }),
      {
        status: 503,
        statusText: "Service Unavailable",
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}

/**
 * Handle messages from clients (cache clearing, etc.)
 */
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }

  if (event.data && event.data.type === "CLEAR_CACHE") {
    console.log("[SW] Clearing cache on client request");
    caches.keys().then((names) => {
      names.forEach((name) => caches.delete(name));
    });
  }

  if (event.data && event.data.type === "CACHE_VERSION_CHECK") {
    // Notify client of current cache version
    event.ports[0].postMessage({ version: CACHE_VERSION });
  }
});

/**
 * Background sync for offline actions (placeholder)
 */
self.addEventListener("sync", (event) => {
  if (event.tag === "sync-analytics") {
    event.waitUntil(syncAnalytics());
  }
});

async function syncAnalytics() {
  try {
    console.log("[SW] Syncing analytics with backend");
    // Implementation for syncing offline analytics
  } catch (error) {
    console.error("[SW] Analytics sync failed:", error);
  }
}

console.log("[SW] Service worker script loaded");
