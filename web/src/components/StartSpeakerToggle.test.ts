import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

import StartSpeakerToggle from "./StartSpeakerToggle.svelte";

describe("StartSpeakerToggle", () => {
  afterEach(() => cleanup());

  it("marks the current speaker as pressed", () => {
    render(StartSpeakerToggle, { value: "user", onselect: vi.fn() });

    expect(screen.getByText("User").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Agent").getAttribute("aria-pressed")).toBe("false");
  });

  it("reports the clicked speaker", async () => {
    const onselect = vi.fn();
    render(StartSpeakerToggle, { value: "agent", onselect });

    await fireEvent.click(screen.getByText("User"));

    expect(onselect).toHaveBeenCalledWith("user");
  });
});
