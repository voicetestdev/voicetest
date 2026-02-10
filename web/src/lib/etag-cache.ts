/**
 * ETag-based cache for fetch requests.
 *
 * Stores response data alongside ETags and includes If-None-Match headers
 * on subsequent requests. Returns cached data on 304 responses.
 */

interface CacheEntry<T> {
  etag: string;
  data: T;
}

export class ETagCache {
  private cache: Map<string, CacheEntry<unknown>> = new Map();

  /**
   * Get cached ETag for a path, if any.
   */
  getETag(path: string): string | undefined {
    return this.cache.get(path)?.etag;
  }

  /**
   * Get cached data for a path, if any.
   */
  getCachedData<T>(path: string): T | undefined {
    return this.cache.get(path)?.data as T | undefined;
  }

  /**
   * Store data with its ETag.
   */
  set<T>(path: string, etag: string, data: T): void {
    this.cache.set(path, { etag, data });
  }

  /**
   * Check if we have cached data for a path.
   */
  has(path: string): boolean {
    return this.cache.has(path);
  }

  /**
   * Clear a specific entry.
   */
  delete(path: string): void {
    this.cache.delete(path);
  }

  /**
   * Clear all cached entries.
   */
  clear(): void {
    this.cache.clear();
  }

  /**
   * Build headers including If-None-Match if cached.
   */
  buildHeaders(path: string, baseHeaders: Record<string, string> = {}): Record<string, string> {
    const headers = { ...baseHeaders };
    const cached = this.cache.get(path);
    if (cached) {
      headers["If-None-Match"] = cached.etag;
    }
    return headers;
  }

  /**
   * Handle a response, returning cached data for 304 or caching new data.
   * Returns null if response should be processed normally.
   */
  handleResponse<T>(path: string, response: Response): T | null {
    // 304 Not Modified - return cached data
    if (response.status === 304) {
      const cached = this.cache.get(path) as CacheEntry<T> | undefined;
      if (cached) {
        return cached.data;
      }
    }
    return null;
  }

  /**
   * Cache response data if it has an ETag.
   */
  cacheResponse<T>(path: string, response: Response, data: T): void {
    const etag = response.headers.get("ETag");
    if (etag) {
      this.set(path, etag, data);
    }
  }
}

// Singleton instance for the app
export const etagCache = new ETagCache();
