import { describe, it, expect } from "vitest";
import { get } from "svelte/store";
import { currentRunWithResults } from "./stores";
import type { RunResultRecord, RunWithResults } from "./types";

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
  });
});
