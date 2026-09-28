/**
 * crypto.randomUUID only exists in secure contexts (https:// or http://localhost).
 * When the app is opened over the LAN (e.g. http://192.168.56.1:3000) the browser
 * leaves it undefined and anything calling it throws "crypto.randomUUID is not a function".
 * getRandomValues IS available in insecure contexts, so build an RFC 4122 v4 UUID from it.
 */
export function installRandomUUIDPolyfill() {
  if (typeof window === "undefined") return;
  const c = window.crypto as Crypto | undefined;
  if (!c || typeof c.getRandomValues !== "function" || typeof c.randomUUID === "function") return;

  const randomUUID = (): `${string}-${string}-${string}-${string}-${string}` => {
    const b = c.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40; // version 4
    b[8] = (b[8] & 0x3f) | 0x80; // RFC 4122 variant
    const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  };

  try {
    Object.defineProperty(c, "randomUUID", { configurable: true, writable: true, value: randomUUID });
  } catch {
    // Some browsers freeze the Crypto instance; patch the prototype instead.
    try {
      Object.defineProperty(Object.getPrototypeOf(c), "randomUUID", { configurable: true, writable: true, value: randomUUID });
    } catch {
      /* nothing else we can do */
    }
  }
}
