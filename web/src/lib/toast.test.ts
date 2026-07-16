import { describe, it, expect, beforeEach, vi } from "vitest";
import { get } from "svelte/store";
import { toasts, pushToast, dismissToast } from "./toast";

describe("toast", () => {
  beforeEach(() => {
    toasts.set([]);
  });

  it("pushToast adds a toast with the message", () => {
    pushToast("something failed");
    const list = get(toasts);
    expect(list).toHaveLength(1);
    expect(list[0].message).toBe("something failed");
  });

  it("assigns distinct ids so toasts do not collide", () => {
    const a = pushToast("one");
    const b = pushToast("two");
    expect(a).not.toBe(b);
    expect(get(toasts)).toHaveLength(2);
  });

  it("dismissToast removes only the matching toast", () => {
    const a = pushToast("one");
    pushToast("two");
    dismissToast(a);
    const list = get(toasts);
    expect(list).toHaveLength(1);
    expect(list[0].message).toBe("two");
  });

  it("auto-dismisses after the timeout", () => {
    vi.useFakeTimers();
    try {
      pushToast("temporary");
      expect(get(toasts)).toHaveLength(1);
      vi.advanceTimersByTime(6000);
      expect(get(toasts)).toHaveLength(0);
    } finally {
      vi.useRealTimers();
    }
  });
});
