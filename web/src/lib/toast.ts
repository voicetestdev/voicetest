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

// Bound how many toasts stack so a burst of rejections can't flood the screen.
const MAX_TOASTS = 5;

let nextId = 1;

export function pushToast(message: string): number {
  const id = nextId++;
  let added = false;
  toasts.update((list) => {
    if (list.some((t) => t.message === message)) return list;
    added = true;
    return [...list, { id, message }].slice(-MAX_TOASTS);
  });
  if (added) {
    setTimeout(() => dismissToast(id), AUTO_DISMISS_MS);
  }
  return id;
}

export function dismissToast(id: number): void {
  toasts.update((list) => list.filter((t) => t.id !== id));
}
