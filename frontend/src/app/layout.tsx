import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

import { SITE_URL } from "@/lib/site";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "ApexRep",
  description: "Apex Legends player stats and tracked match history.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <Link href="/" className="font-semibold tracking-tight">
            ApexRep
          </Link>
        </header>
        {children}
        <footer className="flex flex-col gap-1 border-t border-zinc-200 px-4 py-6 text-sm text-zinc-500 dark:border-zinc-800">
          <p>
            <a
              href="https://apexlegendsstatus.com"
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              Data provided by Apex Legends Status
            </a>
          </p>
          <p>
            ApexRep is a fan site. It is not endorsed by or affiliated with
            Electronic Arts or its licensors.
          </p>
        </footer>
      </body>
    </html>
  );
}
