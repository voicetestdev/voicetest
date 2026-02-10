import { beforeEach, describe, expect, it } from "vitest";
import { ETagCache } from "./etag-cache";

describe("ETagCache", () => {
  let cache: ETagCache;

  beforeEach(() => {
    cache = new ETagCache();
  });

  describe("basic operations", () => {
    it("stores and retrieves data with ETag", () => {
      cache.set("/test", '"abc123"', { value: 42 });

      expect(cache.getETag("/test")).toBe('"abc123"');
      expect(cache.getCachedData("/test")).toEqual({ value: 42 });
      expect(cache.has("/test")).toBe(true);
    });

    it("returns undefined for missing entries", () => {
      expect(cache.getETag("/missing")).toBeUndefined();
      expect(cache.getCachedData("/missing")).toBeUndefined();
      expect(cache.has("/missing")).toBe(false);
    });

    it("deletes specific entries", () => {
      cache.set("/test", '"abc"', { a: 1 });
      cache.set("/other", '"def"', { b: 2 });

      cache.delete("/test");

      expect(cache.has("/test")).toBe(false);
      expect(cache.has("/other")).toBe(true);
    });

    it("clears all entries", () => {
      cache.set("/a", '"1"', {});
      cache.set("/b", '"2"', {});

      cache.clear();

      expect(cache.has("/a")).toBe(false);
      expect(cache.has("/b")).toBe(false);
    });
  });

  describe("buildHeaders", () => {
    it("returns base headers when no cache exists", () => {
      const headers = cache.buildHeaders("/api/data", { Authorization: "Bearer token" });

      expect(headers).toEqual({ Authorization: "Bearer token" });
    });

    it("adds If-None-Match when cache exists", () => {
      cache.set("/api/data", '"etag-123"', { cached: true });

      const headers = cache.buildHeaders("/api/data", { Authorization: "Bearer token" });

      expect(headers).toEqual({
        Authorization: "Bearer token",
        "If-None-Match": '"etag-123"',
      });
    });

    it("works with empty base headers", () => {
      cache.set("/api/data", '"etag-abc"', {});

      const headers = cache.buildHeaders("/api/data");

      expect(headers).toEqual({ "If-None-Match": '"etag-abc"' });
    });
  });

  describe("handleResponse", () => {
    it("returns cached data on 304 response", () => {
      const cachedData = { cached: true, value: 42 };
      cache.set("/api/data", '"etag"', cachedData);

      const mockResponse = { status: 304 } as Response;
      const result = cache.handleResponse<typeof cachedData>("/api/data", mockResponse);

      expect(result).toEqual(cachedData);
    });

    it("returns null on 304 when no cache exists", () => {
      const mockResponse = { status: 304 } as Response;
      const result = cache.handleResponse("/api/data", mockResponse);

      expect(result).toBeNull();
    });

    it("returns null on 200 response", () => {
      cache.set("/api/data", '"etag"', { cached: true });

      const mockResponse = { status: 200 } as Response;
      const result = cache.handleResponse("/api/data", mockResponse);

      expect(result).toBeNull();
    });
  });

  describe("cacheResponse", () => {
    it("caches data when response has ETag header", () => {
      const mockResponse = {
        headers: new Headers({ ETag: '"new-etag"' }),
      } as unknown as Response;

      cache.cacheResponse("/api/data", mockResponse, { value: 123 });

      expect(cache.getETag("/api/data")).toBe('"new-etag"');
      expect(cache.getCachedData("/api/data")).toEqual({ value: 123 });
    });

    it("does not cache when response has no ETag header", () => {
      const mockResponse = {
        headers: new Headers(),
      } as unknown as Response;

      cache.cacheResponse("/api/data", mockResponse, { value: 123 });

      expect(cache.has("/api/data")).toBe(false);
    });

    it("updates existing cache entry", () => {
      cache.set("/api/data", '"old-etag"', { old: true });

      const mockResponse = {
        headers: new Headers({ ETag: '"new-etag"' }),
      } as unknown as Response;

      cache.cacheResponse("/api/data", mockResponse, { new: true });

      expect(cache.getETag("/api/data")).toBe('"new-etag"');
      expect(cache.getCachedData("/api/data")).toEqual({ new: true });
    });
  });
});
