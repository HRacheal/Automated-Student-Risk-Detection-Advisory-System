// Runs synchronously in the browser before React hydration (Next.js file convention).
import { installRandomUUIDPolyfill } from "./lib/polyfills";

installRandomUUIDPolyfill();
