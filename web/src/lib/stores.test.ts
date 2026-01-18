import { describe, it, expect, beforeEach } from "vitest";
import { get } from "svelte/store";
import { currentRunWithResults } from "./stores";
import type { RunResultRecord, RunWithResults } from "./types";

function createResult(overrides: Partial<RunResultRecord> = {}): RunResultRecord {
  return {
    id: overrides.id ?? "result-" + Math.random().toString(36).slice(2),
    run_id: overrides.run_id ?? "run-1",
    test_case_id: overrides.test_case_id ?? "test-1",
    test_name: overrides.test_name ?? "Test",
    status: overrides.status ?? "running",
    duration_ms: overrides.duration_ms ?? null,
    turn_count: overrides.turn_count ?? null,
    end_reason: overrides.end_reason ?? null,
    error_message: overrides.error_message ?? null,
    transcript_json: overrides.transcript_json ?? "[]",
    metrics_json: overrides.metrics_json ?? null,
    nodes_visited: overrides.nodes_visited ?? null,
    tools_called: overrides.tools_called ?? null,
    models_used: overrides.models_used ?? null,
    created_at: overrides.created_at ?? new Date().toISOString(),
  };
}

function createRun(overrides: Partial<RunWithResults> = {}): RunWithResults {
  return {
    id: overrides.id ?? "run-1",
    agent_id: overrides.agent_id ?? "agent-1",
    started_at: overrides.started_at ?? new Date().toISOString(),
    completed_at: overrides.completed_at ?? null,
    results: overrides.results ?? [],
  };
}

describe("stores", () => {
  describe("WebSocket message handling", () => {
    describe("test_started message", () => {
      it("should include test_case_id in the result when test_started is received", () => {
        const testCaseId = "test-case-123";
        const resultId = "result-456";
        const runId = "run-789";

        const initialRun: RunWithResults = {
          id: runId,
          agent_id: "agent-1",
          started_at: new Date().toISOString(),
          completed_at: null,
          results: [],
        };
        currentRunWithResults.set(initialRun);

        currentRunWithResults.update((run) => {
          if (!run) return run;
          const newResult: RunResultRecord = {
            id: resultId,
            run_id: runId,
            test_case_id: testCaseId,
            test_name: "My Test",
            status: "running",
            duration_ms: null,
            turn_count: null,
            end_reason: null,
            error_message: null,
            transcript_json: "[]",
            metrics_json: null,
            nodes_visited: null,
            tools_called: null,
            models_used: null,
            created_at: new Date().toISOString(),
          };
          return {
            ...run,
            results: [...run.results, newResult],
          };
        });

        const run = get(currentRunWithResults);
        expect(run).not.toBeNull();
        expect(run!.results.length).toBe(1);
        expect(run!.results[0].test_case_id).toBe(testCaseId);
        expect(run!.results[0].status).toBe("running");
      });

      it("should not duplicate results when test_started is received twice", () => {
        const resultId = "result-456";
        const runId = "run-789";

        const initialRun: RunWithResults = {
          id: runId,
          agent_id: "agent-1",
          started_at: new Date().toISOString(),
          completed_at: null,
          results: [],
        };
        currentRunWithResults.set(initialRun);

        const addResult = () => {
          currentRunWithResults.update((run) => {
            if (!run) return run;
            const exists = run.results.some((r) => r.id === resultId);
            if (exists) return run;
            const newResult: RunResultRecord = {
              id: resultId,
              run_id: runId,
              test_case_id: "test-1",
              test_name: "My Test",
              status: "running",
              duration_ms: null,
              turn_count: null,
              end_reason: null,
              error_message: null,
              transcript_json: "[]",
              metrics_json: null,
              nodes_visited: null,
              tools_called: null,
              models_used: null,
              created_at: new Date().toISOString(),
            };
            return {
              ...run,
              results: [...run.results, newResult],
            };
          });
        };

        addResult();
        addResult();

        const run = get(currentRunWithResults);
        expect(run!.results.length).toBe(1);
      });
    });

    describe("transcript_update message", () => {
      it("should update transcript_json for the correct result", () => {
        const resultId = "result-456";
        const runId = "run-789";

        const initialRun: RunWithResults = {
          id: runId,
          agent_id: "agent-1",
          started_at: new Date().toISOString(),
          completed_at: null,
          results: [
            {
              id: resultId,
              run_id: runId,
              test_case_id: "test-1",
              test_name: "My Test",
              status: "running",
              duration_ms: null,
              turn_count: null,
              end_reason: null,
              error_message: null,
              transcript_json: "[]",
              metrics_json: null,
              nodes_visited: null,
              tools_called: null,
              models_used: null,
              created_at: new Date().toISOString(),
            },
          ],
        };
        currentRunWithResults.set(initialRun);

        const newTranscript = [
          { role: "assistant", content: "Hello!" },
          { role: "user", content: "Hi there" },
        ];

        currentRunWithResults.update((run) => {
          if (!run) return run;
          return {
            ...run,
            results: run.results.map((r) =>
              r.id === resultId
                ? { ...r, transcript_json: JSON.stringify(newTranscript) }
                : r
            ),
          };
        });

        const run = get(currentRunWithResults);
        expect(run!.results[0].transcript_json).toBe(JSON.stringify(newTranscript));
      });

      it("should not affect other results when updating transcript", () => {
        const runId = "run-789";

        const initialRun: RunWithResults = {
          id: runId,
          agent_id: "agent-1",
          started_at: new Date().toISOString(),
          completed_at: null,
          results: [
            {
              id: "result-1",
              run_id: runId,
              test_case_id: "test-1",
              test_name: "Test 1",
              status: "running",
              duration_ms: null,
              turn_count: null,
              end_reason: null,
              error_message: null,
              transcript_json: "[]",
              metrics_json: null,
              nodes_visited: null,
              tools_called: null,
              models_used: null,
              created_at: new Date().toISOString(),
            },
            {
              id: "result-2",
              run_id: runId,
              test_case_id: "test-2",
              test_name: "Test 2",
              status: "pass",
              duration_ms: 100,
              turn_count: 3,
              end_reason: "completed",
              error_message: null,
              transcript_json: '[{"role":"assistant","content":"Done"}]',
              metrics_json: null,
              nodes_visited: null,
              tools_called: null,
              models_used: null,
              created_at: new Date().toISOString(),
            },
          ],
        };
        currentRunWithResults.set(initialRun);

        currentRunWithResults.update((run) => {
          if (!run) return run;
          return {
            ...run,
            results: run.results.map((r) =>
              r.id === "result-1"
                ? { ...r, transcript_json: '[{"role":"user","content":"Hello"}]' }
                : r
            ),
          };
        });

        const run = get(currentRunWithResults);
        expect(run!.results[1].transcript_json).toBe('[{"role":"assistant","content":"Done"}]');
      });
    });

    describe("state message merging", () => {
      beforeEach(() => {
        currentRunWithResults.set(null);
      });

      it("should preserve running results not yet in server state", () => {
        const runId = "run-1";
        const runningResult = createResult({
          id: "result-running",
          run_id: runId,
          status: "running",
          test_name: "Running Test",
        });

        currentRunWithResults.set(createRun({
          id: runId,
          results: [runningResult],
        }));

        const serverRun = createRun({
          id: runId,
          results: [],
        });

        currentRunWithResults.update((current) => {
          if (!current || current.id !== serverRun.id) {
            return serverRun;
          }
          const serverResultIds = new Set(serverRun.results.map((r) => r.id));
          const runningResultsToKeep = current.results.filter(
            (r) => r.status === "running" && !serverResultIds.has(r.id)
          );
          return {
            ...serverRun,
            results: [...serverRun.results, ...runningResultsToKeep],
          };
        });

        const run = get(currentRunWithResults);
        expect(run!.results.length).toBe(1);
        expect(run!.results[0].id).toBe("result-running");
        expect(run!.results[0].status).toBe("running");
      });

      it("should not duplicate results already in server state", () => {
        const runId = "run-1";
        const sharedResult = createResult({
          id: "result-shared",
          run_id: runId,
          status: "running",
        });

        currentRunWithResults.set(createRun({
          id: runId,
          results: [sharedResult],
        }));

        const serverRun = createRun({
          id: runId,
          results: [{ ...sharedResult, status: "pass" }],
        });

        currentRunWithResults.update((current) => {
          if (!current || current.id !== serverRun.id) {
            return serverRun;
          }
          const serverResultIds = new Set(serverRun.results.map((r) => r.id));
          const runningResultsToKeep = current.results.filter(
            (r) => r.status === "running" && !serverResultIds.has(r.id)
          );
          return {
            ...serverRun,
            results: [...serverRun.results, ...runningResultsToKeep],
          };
        });

        const run = get(currentRunWithResults);
        expect(run!.results.length).toBe(1);
        expect(run!.results[0].status).toBe("pass");
      });

      it("should replace run when IDs don't match", () => {
        currentRunWithResults.set(createRun({
          id: "run-old",
          results: [createResult({ id: "old-result" })],
        }));

        const serverRun = createRun({
          id: "run-new",
          results: [createResult({ id: "new-result" })],
        });

        currentRunWithResults.update((current) => {
          if (!current || current.id !== serverRun.id) {
            return serverRun;
          }
          return current;
        });

        const run = get(currentRunWithResults);
        expect(run!.id).toBe("run-new");
        expect(run!.results.length).toBe(1);
        expect(run!.results[0].id).toBe("new-result");
      });

      it("should not keep completed results that are not in server state", () => {
        const runId = "run-1";
        const completedResult = createResult({
          id: "result-completed",
          run_id: runId,
          status: "pass",
        });

        currentRunWithResults.set(createRun({
          id: runId,
          results: [completedResult],
        }));

        const serverRun = createRun({
          id: runId,
          results: [],
        });

        currentRunWithResults.update((current) => {
          if (!current || current.id !== serverRun.id) {
            return serverRun;
          }
          const serverResultIds = new Set(serverRun.results.map((r) => r.id));
          const runningResultsToKeep = current.results.filter(
            (r) => r.status === "running" && !serverResultIds.has(r.id)
          );
          return {
            ...serverRun,
            results: [...serverRun.results, ...runningResultsToKeep],
          };
        });

        const run = get(currentRunWithResults);
        expect(run!.results.length).toBe(0);
      });
    });

    describe("run ID validation", () => {
      beforeEach(() => {
        currentRunWithResults.set(null);
      });

      it("should not add test_started result to wrong run", () => {
        const currentRunId = "run-current";
        const wrongRunId = "run-wrong";

        currentRunWithResults.set(createRun({
          id: currentRunId,
          results: [],
        }));

        const handleTestStarted = (runId: string, data: { result_id: string; test_name: string }) => {
          currentRunWithResults.update((run) => {
            if (!run) return run;
            if (run.id !== runId) return run;
            const exists = run.results.some((r) => r.id === data.result_id);
            if (exists) return run;
            return {
              ...run,
              results: [...run.results, createResult({
                id: data.result_id,
                run_id: runId,
                test_name: data.test_name,
              })],
            };
          });
        };

        handleTestStarted(wrongRunId, { result_id: "result-1", test_name: "Test" });

        const run = get(currentRunWithResults);
        expect(run!.results.length).toBe(0);
      });

      it("should not update transcript for wrong run", () => {
        const currentRunId = "run-current";
        const wrongRunId = "run-wrong";
        const resultId = "result-1";

        currentRunWithResults.set(createRun({
          id: currentRunId,
          results: [createResult({ id: resultId, run_id: currentRunId, transcript_json: "[]" })],
        }));

        const handleTranscriptUpdate = (runId: string, data: { result_id: string; transcript: unknown[] }) => {
          currentRunWithResults.update((run) => {
            if (!run || run.id !== runId) return run;
            return {
              ...run,
              results: run.results.map((r) =>
                r.id === data.result_id
                  ? { ...r, transcript_json: JSON.stringify(data.transcript) }
                  : r
              ),
            };
          });
        };

        handleTranscriptUpdate(wrongRunId, {
          result_id: resultId,
          transcript: [{ role: "user", content: "Hello" }],
        });

        const run = get(currentRunWithResults);
        expect(run!.results[0].transcript_json).toBe("[]");
      });
    });
  });
});
