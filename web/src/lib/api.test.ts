import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, configureApi } from "./api";
import type { MetricsConfig } from "./types";

describe("api", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn();
    configureApi({ baseUrl: "/api", getHeaders: undefined });
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe("getMetricsConfig", () => {
    it("should fetch metrics config for an agent", async () => {
      const mockConfig: MetricsConfig = {
        threshold: 0.8,
        global_metrics: [
          {
            name: "HIPAA",
            criteria: "Check compliance",
            enabled: true,
          },
        ],
      };

      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: () => Promise.resolve(JSON.stringify(mockConfig)),
      });

      const result = await api.getMetricsConfig("agent-123");

      expect(global.fetch).toHaveBeenCalledWith("/api/agents/agent-123/metrics-config", { headers: {} });
      expect(result).toEqual(mockConfig);
    });

    it("should throw on error response", async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        statusText: "Not Found",
        text: () => Promise.resolve("Agent not found"),
      });

      await expect(api.getMetricsConfig("nonexistent")).rejects.toThrow("Agent not found");
    });
  });

  describe("updateMetricsConfig", () => {
    it("should update metrics config for an agent", async () => {
      const inputConfig: MetricsConfig = {
        threshold: 0.9,
        global_metrics: [
          {
            name: "PCI",
            criteria: "Check PCI compliance",
            threshold: 0.95,
            enabled: true,
          },
        ],
      };

      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(inputConfig)),
      });

      const result = await api.updateMetricsConfig("agent-456", inputConfig);

      expect(global.fetch).toHaveBeenCalledWith(
        "/api/agents/agent-456/metrics-config",
        expect.objectContaining({
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(inputConfig),
        })
      );
      expect(result).toEqual(inputConfig);
    });

    it("should throw on error response", async () => {
      const config: MetricsConfig = {
        threshold: 0.7,
        global_metrics: [],
      };

      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        statusText: "Bad Request",
        text: () => Promise.resolve("Invalid threshold"),
      });

      await expect(api.updateMetricsConfig("agent-123", config)).rejects.toThrow("Invalid threshold");
    });
  });

  describe("deleteRun", () => {
    it("should delete a run", async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ status: "deleted", id: "run-123" })),
      });

      const result = await api.deleteRun("run-123");

      expect(global.fetch).toHaveBeenCalledWith(
        "/api/runs/run-123",
        expect.objectContaining({ method: "DELETE", headers: {} })
      );
      expect(result).toEqual({ status: "deleted", id: "run-123" });
    });

    it("should throw on error response", async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        statusText: "Not Found",
        text: () => Promise.resolve("Run not found"),
      });

      await expect(api.deleteRun("nonexistent")).rejects.toThrow("Run not found");
    });

    it("should throw when deleting active run", async () => {
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        ok: false,
        statusText: "Bad Request",
        text: () => Promise.resolve("Cannot delete an active run"),
      });

      await expect(api.deleteRun("active-run")).rejects.toThrow("Cannot delete an active run");
    });
  });
});
