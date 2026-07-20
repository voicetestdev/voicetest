/**
 * Extract a human-readable message from an unknown thrown value.
 *
 * For a non-Error value, returns a non-empty `fallback` when given, else the
 * stringified value.
 */
export function errorMessage(e: unknown, fallback?: string): string {
  if (e instanceof Error) return e.message;
  return fallback || String(e);
}

/**
 * Message to show a user for an unhandled promise rejection, or null to ignore
 * it. Skips value-less rejections and aborted/superseded requests, which are
 * noise rather than actionable errors.
 */
export function rejectionMessage(reason: unknown): string | null {
  if (reason == null) return null;
  if (typeof reason === "object" && (reason as { name?: unknown }).name === "AbortError") {
    return null;
  }
  return errorMessage(reason) || null;
}
