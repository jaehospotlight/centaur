import Link from "next/link";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata = {
  title: "Paradigm AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="m-0 bg-zinc-950 antialiased font-sans">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-zinc-900 focus:text-zinc-100 focus:px-3 focus:py-2 focus:rounded-md focus:outline-none focus:ring-2 focus:ring-sky-400"
        >
          Skip to main content
        </a>
        <nav className="flex items-center gap-6 px-6 py-2.5 border-b border-zinc-800/50 bg-zinc-950/95 backdrop-blur-sm font-sans z-50 shrink-0">
          <Link
            href="/"
            className="text-zinc-50 no-underline font-semibold text-[13px] tracking-tight rounded-sm"
          >
            Paradigm AI
          </Link>
          <Link
            href="/threads"
            className="text-zinc-500 no-underline text-[13px] font-medium hover:text-zinc-300 transition-colors rounded-sm"
          >
            Threads
          </Link>
        </nav>
        <main id="main-content">{children}</main>
      </body>
    </html>
  );
}
