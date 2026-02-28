import Link from "next/link";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata = {
  title: "Paradigm AI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="m-0 bg-background text-foreground antialiased font-sans">
        <TooltipProvider>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-card focus:text-foreground focus:px-3 focus:py-2 focus:rounded-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            Skip to main content
          </a>
          <nav className="flex items-center gap-6 px-6 py-2.5 border-b border-border bg-background/95 backdrop-blur-sm font-sans z-50 shrink-0">
            <Link
              href="/"
              className="text-foreground no-underline font-semibold text-[13px] tracking-tight rounded-sm"
            >
              Paradigm AI
            </Link>
            <Link
              href="/threads"
              className="text-muted-foreground no-underline text-[13px] font-medium hover:text-foreground transition-colors rounded-sm"
            >
              Threads
            </Link>
          </nav>
          <main id="main-content">{children}</main>
          <Toaster position="top-right" richColors closeButton />
        </TooltipProvider>
      </body>
    </html>
  );
}
