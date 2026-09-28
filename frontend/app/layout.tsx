import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "My Coach · Student Risk Detection & Advisory",
  description: "USIU academic advising: automated student risk detection from RosarioSIS and Moodle data",
};

// crypto.randomUUID is missing in non-secure contexts (e.g. http://192.168.x.x:3000).
// instrumentation-client.ts installs the polyfill before hydration; this inline copy runs
// even earlier (while the <head> is parsed) so scripts that load before the app bundle
// are covered too. Keep both in sync with lib/polyfills.ts.
const randomUUIDPolyfill = `
(function () {
  var c = typeof window !== "undefined" ? window.crypto : undefined;
  if (!c || typeof c.getRandomValues !== "function" || typeof c.randomUUID === "function") return;
  var fn = function () {
    var b = c.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 15) | 64;
    b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return (x < 16 ? "0" : "") + x.toString(16); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  };
  try { Object.defineProperty(c, "randomUUID", { configurable: true, writable: true, value: fn }); }
  catch (e) { try { Object.defineProperty(Object.getPrototypeOf(c), "randomUUID", { configurable: true, writable: true, value: fn }); } catch (e2) {} }
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: randomUUIDPolyfill }} />
      </head>
      <body suppressHydrationWarning className="min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
