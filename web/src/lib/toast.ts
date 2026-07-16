/**
 * Transient, non-fatal notifications surfaced as dismissable toasts.
 */

import { writable } from "svelte/store";

export interface Toast {
  id: number;
  message: string;
}

export const toasts = writable<Toast[]>([]);

const AUTO_DISMISS_MS = 6000;

let nextId = 1;

export function pushToast(message: string): number {
  const id = nextId++;
  toasts.update((list) => [...list, { id, message }]);
  if (typeof setTimeout === "function") {
    setTimeout(() => dismissToast(id), AUTO_DISMISS_MS);
  }
  return id;
}

export function dismissToast(id: number): void {
  toasts.update((list) => list.filter((t) => t.id !== id));
}
