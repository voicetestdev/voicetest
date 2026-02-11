import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/svelte";
import { get } from "svelte/store";

// Mock the API module completely
vi.mock("../lib/api", () => ({
  api: {
    listAgents: () => Promise.resolve([]),
    getAgentGraph: () => Promise.resolve({ nodes: [], edges: [] }),
    listTestsForAgent: () => Promise.resolve([]),
    listRunsForAgent: () => Promise.resolve([]),
    getSettings: () => Promise.resolve({
      agent_model: "test-model",
      simulator_model: "test-model",
      judge_model: "test-model",
      max_turns: 10,
      streaming: false,
    }),
    startRun: () => Promise.resolve({
      id: "run-123",
      agent_id: "agent-1",
      started_at: new Date().toISOString(),
    }),
    listImporters: () => Promise.resolve([]),
    listExporters: () => Promise.resolve([]),
    listPlatforms: () => Promise.resolve([]),
  },
}));

// Mock WebSocket-related store functions
vi.mock("../lib/stores", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/stores")>();
  return {
    ...actual,
    startRun: () => Promise.resolve("run-123"),
    connectRunWebSocket: () => {},
    disconnectRunWebSocket: () => {},
    initStores: () => Promise.resolve(undefined),
  };
});

import {
  currentView,
  currentAgentId,
  agents,
  agentGraph,
  testCases,
  testCaseRecords,
  runHistory,
  isRunning,
  settings,
} from "../lib/stores";
import TestsView from "./TestsView.svelte";
import App from "../App.svelte";

describe("TestsView - Run Selected", () => {
  beforeEach(() => {
    // Set up stores with an agent and tests
    currentAgentId.set("agent-1");
    agentGraph.set({
      nodes: {},
      entry_node_id: "start",
      source_type: "custom",
      source_metadata: {},
    });
    isRunning.set(false);
    currentView.set("tests");

    // Add test cases
    const testRecord = {
      id: "test-1",
      agent_id: "agent-1",
      name: "Test Case 1",
      user_prompt: "Hello, book an appointment",
      metrics: '["Agent should greet user"]',
      dynamic_variables: "{}",
      tool_mocks: "[]",
      type: "llm",
      llm_model: null,
      includes: null,
      excludes: null,
      patterns: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      source_path: null,
      source_index: null,
    };
    testCaseRecords.set([testRecord]);
    testCases.set([
      {
        name: "Test Case 1",
        user_prompt: "Hello, book an appointment",
        metrics: ["Agent should greet user"],
        dynamic_variables: {},
        tool_mocks: [],
        type: "llm",
        includes: [],
        excludes: [],
        patterns: [],
      },
    ]);

    // Mock localStorage
    const localStorageMock = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
    };
    Object.defineProperty(window, "localStorage", { value: localStorageMock, writable: true });

    // Mock matchMedia
    Object.defineProperty(window, "matchMedia", {
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
      writable: true,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    // Reset stores
    currentView.set("tests");
    currentAgentId.set(null);
    testCaseRecords.set([]);
    testCases.set([]);
    isRunning.set(false);
  });

  it("should update currentView store when Run Selected is clicked", async () => {
    render(TestsView);

    // Verify we start on tests view
    expect(get(currentView)).toBe("tests");

    // Find and click the checkbox to select the test
    const checkboxes = screen.getAllByRole("checkbox");
    await fireEvent.click(checkboxes[1]); // Click the test checkbox

    // Click the Run Selected button
    const runSelectedBtn = screen.getByRole("button", { name: /Run Selected/i });
    await fireEvent.click(runSelectedBtn);

    // The store should now be "runs"
    await waitFor(() => {
      expect(get(currentView)).toBe("runs");
    });
  });

  it("should have Run Selected button enabled when a test is selected", async () => {
    render(TestsView);

    // Initially disabled
    let runSelectedBtn = screen.getByRole("button", { name: /Run Selected/i });
    expect(runSelectedBtn.hasAttribute("disabled")).toBe(true);

    // Select a test
    const checkboxes = screen.getAllByRole("checkbox");
    await fireEvent.click(checkboxes[1]);

    // Now should be enabled
    runSelectedBtn = screen.getByRole("button", { name: /Run Selected/i });
    expect(runSelectedBtn.hasAttribute("disabled")).toBe(false);
  });
});

describe("App - View switching reactivity", () => {
  beforeEach(() => {
    // Set up complete app state BEFORE rendering
    agents.set([
      {
        id: "agent-1",
        name: "Test Agent",
        source_type: "custom",
        source_path: null,
        tests_paths: null,
        graph_json: null,
        metrics_config: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    currentAgentId.set("agent-1");
    agentGraph.set({
      nodes: {},
      entry_node_id: "start",
      source_type: "custom",
      source_metadata: {},
    });
    settings.set({
      models: {
        agent: "test-model",
        simulator: "test-model",
        judge: "test-model",
      },
      run: {
        max_turns: 10,
        verbose: false,
        flow_judge: false,
        streaming: false,
        test_model_precedence: false,
      },
      env: {},
    });
    runHistory.set([]);
    isRunning.set(false);
    currentView.set("tests");
    testCaseRecords.set([]);
    testCases.set([]);

    // Mock localStorage
    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: vi.fn().mockReturnValue(null),
        setItem: vi.fn(),
      },
      writable: true,
    });

    // Mock matchMedia
    Object.defineProperty(window, "matchMedia", {
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
      writable: true,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    currentView.set("import");
    currentAgentId.set(null);
    agents.set([]);
    testCaseRecords.set([]);
    testCases.set([]);
    runHistory.set([]);
    isRunning.set(false);
    settings.set(null);
  });

  it("App should update the active tab when currentView store changes", async () => {
    // This test verifies that App.svelte re-renders when the store changes
    // THIS IS THE BUG: the store changes but the UI doesn't update

    render(App);

    // Wait for app to initialize (mocked initStores resolves immediately)
    await waitFor(() => {
      // Look for the view tabs which indicate the app is initialized with an agent
      const tabButtons = screen.getAllByRole("button");
      const testsTab = tabButtons.find(btn => btn.textContent?.includes("Tests"));
      expect(testsTab).toBeDefined();
    });

    // Verify Tests tab is currently active
    let testsTab = screen.getAllByRole("button").find(btn => btn.textContent?.includes("Tests"));
    expect(testsTab?.classList.contains("active")).toBe(true);

    // Change the store (this is what runSelectedTests does)
    currentView.set("runs");

    // Verify the store actually changed
    expect(get(currentView)).toBe("runs");

    // THE BUG: The Runs tab should now be active, but if the bug exists, Tests tab stays active
    await waitFor(() => {
      const runsTab = screen.getAllByRole("button").find(btn => btn.textContent?.includes("Runs"));
      expect(runsTab?.classList.contains("active")).toBe(true);
    }, { timeout: 500 });
  });

  it("App should switch from TestsView to RunsView when store changes", async () => {
    render(App);

    // Wait for app to show the tests view content
    await waitFor(() => {
      // TestsView shows "Tests for {agent name}" or similar content
      const content = document.body.textContent;
      expect(content).toContain("Tests");
    });

    // Verify we're showing TestsView (it has "Run All" button)
    expect(screen.getByRole("button", { name: /Run All/i })).toBeDefined();

    // Change the view store
    currentView.set("runs");

    // THE BUG: If the store change doesn't trigger re-render,
    // we'll still see "Run All" button from TestsView instead of RunsView content
    await waitFor(() => {
      // RunsView should be visible now - it doesn't have "Run All" button
      // Instead it might show "No runs yet" or run history
      const runAllButtons = screen.queryAllByRole("button", { name: /Run All/i });
      // If view switched correctly, Run All button should be gone (it's in TestsView only)
      expect(runAllButtons.length).toBe(0);
    }, { timeout: 500 });
  });
});
