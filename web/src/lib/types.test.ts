import { describe, it, expect } from "vitest";
import type { GlobalMetric, MetricsConfig, MetricResult } from "./types";

describe("types", () => {
  describe("GlobalMetric", () => {
    it("should allow creating a minimal global metric", () => {
      const metric: GlobalMetric = {
        name: "HIPAA Compliance",
        criteria: "Agent must verify patient identity",
        enabled: true,
      };

      expect(metric.name).toBe("HIPAA Compliance");
      expect(metric.criteria).toBe("Agent must verify patient identity");
      expect(metric.enabled).toBe(true);
      expect(metric.threshold).toBeUndefined();
    });

    it("should allow creating a global metric with threshold override", () => {
      const metric: GlobalMetric = {
        name: "Strict Check",
        criteria: "Must pass with high confidence",
        threshold: 0.9,
        enabled: true,
      };

      expect(metric.threshold).toBe(0.9);
    });

    it("should allow null threshold", () => {
      const metric: GlobalMetric = {
        name: "Default Threshold",
        criteria: "Uses agent default",
        threshold: null,
        enabled: true,
      };

      expect(metric.threshold).toBeNull();
    });

    it("should allow disabled metrics", () => {
      const metric: GlobalMetric = {
        name: "Disabled Metric",
        criteria: "Should not run",
        enabled: false,
      };

      expect(metric.enabled).toBe(false);
    });
  });

  describe("MetricsConfig", () => {
    it("should allow creating an empty config with default threshold", () => {
      const config: MetricsConfig = {
        threshold: 0.7,
        global_metrics: [],
      };

      expect(config.threshold).toBe(0.7);
      expect(config.global_metrics).toHaveLength(0);
    });

    it("should allow creating a config with multiple global metrics", () => {
      const config: MetricsConfig = {
        threshold: 0.8,
        global_metrics: [
          {
            name: "HIPAA",
            criteria: "Check HIPAA compliance",
            enabled: true,
          },
          {
            name: "PCI",
            criteria: "Check PCI compliance",
            threshold: 0.95,
            enabled: true,
          },
          {
            name: "Disabled",
            criteria: "This is disabled",
            enabled: false,
          },
        ],
      };

      expect(config.threshold).toBe(0.8);
      expect(config.global_metrics).toHaveLength(3);
      expect(config.global_metrics[0].name).toBe("HIPAA");
      expect(config.global_metrics[1].threshold).toBe(0.95);
      expect(config.global_metrics[2].enabled).toBe(false);
    });
  });

  describe("MetricResult", () => {
    it("should allow creating a result with score and threshold", () => {
      const result: MetricResult = {
        metric: "Agent greeted user",
        passed: true,
        reasoning: "The agent said hello",
        score: 0.95,
        threshold: 0.7,
        confidence: 0.9,
      };

      expect(result.score).toBe(0.95);
      expect(result.threshold).toBe(0.7);
      expect(result.passed).toBe(true);
    });

    it("should allow creating a result without score (backwards compatible)", () => {
      const result: MetricResult = {
        metric: "Legacy metric",
        passed: false,
        reasoning: "Did not pass",
      };

      expect(result.score).toBeUndefined();
      expect(result.threshold).toBeUndefined();
      expect(result.confidence).toBeUndefined();
    });

    it("should correctly represent a failing metric", () => {
      const result: MetricResult = {
        metric: "Check compliance",
        passed: false,
        reasoning: "Score below threshold",
        score: 0.5,
        threshold: 0.7,
      };

      expect(result.passed).toBe(false);
      expect(result.score).toBeLessThan(result.threshold!);
    });
  });
});
