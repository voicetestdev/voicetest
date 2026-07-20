import { describe, it, expect } from "vitest";
import { errorMessage, rejectionMessage } from "./errors";

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

  it("degrades an empty fallback to the stringified value", () => {
    expect(errorMessage(42, "")).toBe("42");
  });
});

describe("rejectionMessage", () => {
  it("returns null for a null/undefined reason", () => {
    expect(rejectionMessage(undefined)).toBeNull();
    expect(rejectionMessage(null)).toBeNull();
  });

  it("returns null for an AbortError (cancelled/superseded request)", () => {
    expect(rejectionMessage(new DOMException("aborted", "AbortError"))).toBeNull();
  });

  it("returns null for an empty message", () => {
    expect(rejectionMessage("")).toBeNull();
  });

  it("returns the message for a real error", () => {
    expect(rejectionMessage(new Error("boom"))).toBe("boom");
  });
});
