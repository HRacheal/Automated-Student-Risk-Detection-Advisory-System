import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "My Coach",
  description: "Unified Rule Engine & Advisory Assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning className="antialiased">
        {children}
      </body>
    </html>
  );
}