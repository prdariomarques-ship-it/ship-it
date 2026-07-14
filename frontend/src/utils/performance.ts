/**
 * Real User Monitoring (RUM) - Frontend performance instrumentation
 *
 * Collects Core Web Vitals and sends to backend for OBS-003 monitoring:
 * - First Contentful Paint (FCP): Time to first content on screen
 * - Largest Contentful Paint (LCP): Time to largest content element
 * - Cumulative Layout Shift (CLS): Visual stability metric
 * - Time to Interactive (TTI): Time to interactive state
 */

// import { getCLS, getFCP, getFID, getLCP, getTTFB, Metric } from "web-vitals";

export interface PerformanceMetric {
  name: string;
  value: number;
  units: string;
  timestamp: number;
  url: string;
  userAgent: string;
}

export interface BundleMetrics {
  totalSize: number;
  gzippedSize: number;
  chunks: ChunkMetric[];
  timestamp: number;
}

export interface ChunkMetric {
  name: string;
  size: number;
  gzippedSize: number;
}

class PerformanceMonitor {
  private metrics: Map<string, PerformanceMetric> = new Map();
  private enabled: boolean = true;
  private batchSize: number = 10;
  private flushInterval: number = 30000; // 30 seconds
  private metricBatch: PerformanceMetric[] = [];

  constructor() {
    this.initializeWebVitals();
    this.startAutoFlush();
  }

  /**
   * Initialize Web Vitals collection
   */
  private initializeWebVitals(): void {
    if (!this.enabled || typeof window === "undefined") {
      return;
    }

    // Web Vitals collection disabled - web-vitals package not installed
    // Uncomment the following code if web-vitals package is added to dependencies:
    /*
    // First Contentful Paint
    getFCP((metric: Metric) => {
      this.recordMetric("FCP", metric.value, "ms");
    });

    // Largest Contentful Paint
    getLCP((metric: Metric) => {
      this.recordMetric("LCP", metric.value, "ms");
    });

    // First Input Delay
    getFID((metric: Metric) => {
      this.recordMetric("FID", metric.value, "ms");
    });

    // Cumulative Layout Shift
    getCLS((metric: Metric) => {
      this.recordMetric("CLS", metric.value, "unitless");
    });

    // Time to First Byte
    getTTFB((metric: Metric) => {
      this.recordMetric("TTFB", metric.value, "ms");
    });
    */
  }

  /**
   * Record a performance metric
   */
  private recordMetric(
    name: string,
    value: number,
    units: string
  ): void {
    const metric: PerformanceMetric = {
      name,
      value,
      units,
      timestamp: Date.now(),
      url: typeof window !== "undefined" ? window.location.href : "",
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "",
    };

    this.metrics.set(name, metric);
    this.metricBatch.push(metric);

    // Auto-flush if batch is full
    if (this.metricBatch.length >= this.batchSize) {
      this.flush();
    }
  }

  /**
   * Measure Navigation Timing (from Navigation Timing API)
   */
  public getNavigationTiming(): Record<string, number> {
    if (typeof window === "undefined" || !window.performance) {
      return {};
    }

    const perfData = window.performance.timing;
    const pageLoadTime =
      perfData.loadEventEnd - perfData.navigationStart;
    const connectTime =
      perfData.responseEnd - perfData.requestStart;
    const renderTime =
      perfData.domComplete - perfData.domLoading;
    const domInteractiveTime =
      perfData.domInteractive - perfData.navigationStart;

    return {
      pageLoadTime,
      connectTime,
      renderTime,
      domInteractiveTime,
    };
  }

  /**
   * Measure route navigation performance
   */
  public startRouteNavigation(routeName: string): () => void {
    const startTime = performance.now();

    return () => {
      const duration = performance.now() - startTime;
      this.recordMetric(`ROUTE_${routeName}`, duration, "ms");
    };
  }

  /**
   * Measure component render time
   */
  public measureComponent(componentName: string): () => void {
    const startTime = performance.now();
    performance.mark(`${componentName}-start`);

    return () => {
      const duration = performance.now() - startTime;
      performance.mark(`${componentName}-end`);
      performance.measure(
        componentName,
        `${componentName}-start`,
        `${componentName}-end`
      );
      this.recordMetric(`COMPONENT_${componentName}`, duration, "ms");
    };
  }

  /**
   * Measure async operation (API call, etc.)
   */
  public async measureAsync<T>(
    operationName: string,
    operation: () => Promise<T>
  ): Promise<T> {
    const startTime = performance.now();

    try {
      return await operation();
    } finally {
      const duration = performance.now() - startTime;
      this.recordMetric(`ASYNC_${operationName}`, duration, "ms");
    }
  }

  /**
   * Get all collected metrics
   */
  public getMetrics(): Record<string, PerformanceMetric> {
    const result: Record<string, PerformanceMetric> = {};
    this.metrics.forEach((metric, name) => {
      result[name] = metric;
    });
    return result;
  }

  /**
   * Send metrics to backend
   */
  public async sendMetrics(
    endpoint: string = "/api/performance/metrics"
  ): Promise<void> {
    if (!this.enabled || this.metricBatch.length === 0) {
      return;
    }

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          metrics: this.metricBatch,
          timestamp: Date.now(),
          url: typeof window !== "undefined" ? window.location.href : "",
        }),
      });

      if (response.ok) {
        this.metricBatch = [];
      }
    } catch (error) {
      console.error("Failed to send performance metrics:", error);
    }
  }

  /**
   * Flush metrics to backend
   */
  public async flush(): Promise<void> {
    await this.sendMetrics();
  }

  /**
   * Start auto-flush interval
   */
  private startAutoFlush(): void {
    if (typeof window === "undefined") {
      return;
    }

    setInterval(() => {
      if (this.metricBatch.length > 0) {
        this.flush();
      }
    }, this.flushInterval);
  }

  /**
   * Enable/disable monitoring
   */
  public setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  /**
   * Clear collected metrics
   */
  public clear(): void {
    this.metrics.clear();
    this.metricBatch = [];
  }
}

// Singleton instance
let performanceMonitor: PerformanceMonitor | null = null;

export function initializePerformanceMonitoring(): PerformanceMonitor {
  if (!performanceMonitor) {
    performanceMonitor = new PerformanceMonitor();
  }
  return performanceMonitor;
}

export function getPerformanceMonitor(): PerformanceMonitor {
  if (!performanceMonitor) {
    throw new Error(
      "Performance monitor not initialized. Call initializePerformanceMonitoring() first."
    );
  }
  return performanceMonitor;
}

/**
 * React hook for performance monitoring
 */
export function usePerformanceMonitoring() {
  const monitor = getPerformanceMonitor();

  return {
    recordMetric: (name: string, value: number, units?: string) => {
      // @ts-ignore - recordMetric is private but we expose it via hook
      monitor.recordMetric(name, value, units || "ms");
    },
    measureComponent: (componentName: string) => {
      return monitor.measureComponent(componentName);
    },
    measureAsync: <T,>(
      operationName: string,
      operation: () => Promise<T>
    ) => {
      return monitor.measureAsync(operationName, operation);
    },
    getMetrics: () => monitor.getMetrics(),
    sendMetrics: () => monitor.sendMetrics(),
  };
}

/**
 * Track page visibility changes for RUM
 */
export function initializeVisibilityTracking(): void {
  if (typeof document === "undefined") {
    return;
  }

  document.addEventListener("visibilitychange", () => {
    const monitor = getPerformanceMonitor();
    if (document.hidden) {
      // Page hidden - flush metrics
      monitor.flush().catch((error) => {
        console.error("Failed to flush metrics on page hide:", error);
      });
    }
  });
}

/**
 * Send metrics before page unload
 */
export function initializeUnloadTracking(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.addEventListener("beforeunload", () => {
    const monitor = getPerformanceMonitor();
    // Use sendBeacon for reliability during page unload
    const metrics = Object.values(monitor.getMetrics());
    if (metrics.length > 0 && navigator.sendBeacon) {
      navigator.sendBeacon(
        "/api/performance/metrics",
        JSON.stringify({ metrics, timestamp: Date.now() })
      );
    }
  });
}

/**
 * Initialize all performance tracking
 */
export function initializeAllPerformanceTracking(): void {
  initializePerformanceMonitoring();
  initializeVisibilityTracking();
  initializeUnloadTracking();
}
