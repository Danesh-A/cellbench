import "./globals.css";
import Link from "next/link";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "CellBench",
  description: "A self-hosted benchmarking platform for single-cell perturbation models.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-ink antialiased">
        <header className="border-b border-slate-200">
          <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="font-semibold tracking-tight">
              CellBench
            </Link>
            <ul className="flex gap-6 text-sm text-slate-600">
              <li><Link href="/challenges">Challenges</Link></li>
              <li><Link href="/datasets">Datasets</Link></li>
              <li><Link href="/models">Models</Link></li>
              <li><Link href="/dashboard">Dashboard</Link></li>
              <li><Link href="/login" className="text-accent">Sign in</Link></li>
            </ul>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-slate-500">
          CellBench is a portfolio demo. See <code>DESIGN.md</code> for architecture.
        </footer>
      </body>
    </html>
  );
}
