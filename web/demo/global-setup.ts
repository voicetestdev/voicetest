/**
 * Playwright globalSetup — runs once before any test/recording starts.
 *
 * Clears all existing agents, seeds showcase agents, and configures the
 * groq model so demos have a clean left nav with interesting agents.
 */

import healthcareAgent from "../../voicetest/demo/agent.json" with { type: "json" };
import travelAgent from "../../voicetest/demo/travel-agent.json" with { type: "json" };
import helpdeskAgent from "../../voicetest/demo/helpdesk-agent.json" with { type: "json" };
import insuranceAgent from "./dry-agent.json" with { type: "json" };
import demoTests from "../../voicetest/demo/tests.json" with { type: "json" };

const BASE = "http://localhost:8000";

const SHOWCASE_AGENTS = [
  { name: "Acme Healthcare", config: healthcareAgent, source: "retell-llm", loadTests: true },
  { name: "Meridian Insurance", config: insuranceAgent, source: "retell-llm", loadTests: false },
  { name: "Skyline Travel", config: travelAgent, source: "retell-llm", loadTests: false },
  { name: "TechCorp IT Support", config: helpdeskAgent, source: "retell-llm", loadTests: false },
];

async function api(method: string, path: string, body?: unknown, ignoreErrors = false): Promise<unknown> {
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok && resp.status !== 404 && !ignoreErrors) {
    throw new Error(`${method} ${path} failed: ${resp.status}`);
  }
  return resp.json().catch(() => null);
}

export default async function globalSetup() {
  // Delete all existing agents and their child records (tests, runs)
  const agents = (await api("GET", "/api/agents")) as { id: string }[];
  for (const agent of agents) {
    // Delete runs first (they reference agents via FK)
    const runs = (await api("GET", `/api/agents/${agent.id}/runs`)) as { id: string }[];
    if (runs) {
      for (const run of runs) {
        await api("DELETE", `/api/runs/${run.id}`, undefined, true);
      }
    }
    // Delete test cases (they reference agents via FK)
    const tests = (await api("GET", `/api/agents/${agent.id}/tests`)) as { id: string }[];
    if (tests) {
      for (const test of tests) {
        await api("DELETE", `/api/tests/${test.id}`, undefined, true);
      }
    }
    await api("DELETE", `/api/agents/${agent.id}`, undefined, true);
  }

  // Create showcase agents
  for (const { name, config, source, loadTests } of SHOWCASE_AGENTS) {
    const created = (await api("POST", "/api/agents", { name, config, source })) as { id: string };

    // Load demo test cases onto the healthcare agent
    if (loadTests) {
      for (const testCase of demoTests) {
        await api("POST", `/api/agents/${created.id}/tests`, testCase);
      }
    }
  }

  // Configure groq model — merge into existing settings to preserve env keys
  const current = (await api("GET", "/api/settings")) as Record<string, unknown>;
  await api("PUT", "/api/settings", {
    ...current,
    models: {
      agent: "groq/llama-3.1-8b-instant",
      judge: "groq/llama-3.1-8b-instant",
    },
  });
}
