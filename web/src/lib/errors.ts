/**
 * Extract a human-readable message from an unknown thrown value.
 *
 * For a non-Error value, returns `fallback` when given, else the stringified
 * value.
 */
export function errorMessage(e: unknown, fallback?: string): string {
  if (e instanceof Error) return e.message;
  return fallback ?? String(e);
}
