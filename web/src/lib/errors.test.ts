import { describe, it, expect } from "vitest";
import { errorMessage } from "./errors";

describe("errorMessage", () => {
  it("returns the message of an Error", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });

  it("stringifies a non-Error value", () => {
    expect(errorMessage("plain string")).toBe("plain string");
    expect(errorMessage(42)).toBe("42");
  });

  it("uses the fallback for a non-Error value when given", () => {
    expect(errorMessage(undefined, "Failed to load")).toBe("Failed to load");
  });

  it("prefers the Error's message over the fallback", () => {
    expect(errorMessage(new Error("real"), "fallback")).toBe("real");
  });
});
