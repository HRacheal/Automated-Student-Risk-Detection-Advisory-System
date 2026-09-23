/**
 * Safe UUID generator that falls back to pseudo-random string generation
 * if native Web Crypto API (crypto.randomUUID) is unavailable.
 */
export function generateUUID(): string {
  if (
    typeof window !== "undefined" &&
    window.crypto &&
    typeof window.crypto.randomUUID === "function"
  ) {
    return window.crypto.randomUUID();
  }

  // Fallback for non-secure contexts (HTTP over custom IP addresses)
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) => {
    const num = Number(c);
    return (
      num ^
      (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (num / 4)))
    ).toString(16);
  });
}