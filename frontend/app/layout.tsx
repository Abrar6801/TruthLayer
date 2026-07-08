import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "TruthLayer — AI fact-checker with citations",
  description:
    "Paste a factual claim; TruthLayer searches the web, weighs the evidence, and returns a cited verdict. A demo project for learning agentic RAG.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Privacy-respecting analytics (Plausible: no cookies, no PII, page views
  // and events only). Loads ONLY when the site owner sets
  // NEXT_PUBLIC_PLAUSIBLE_DOMAIN — the value is just the site's own domain,
  // which is public by definition, so NEXT_PUBLIC_ is appropriate here.
  const plausibleDomain = process.env.NEXT_PUBLIC_PLAUSIBLE_DOMAIN;
  return (
    <html lang="en">
      <head>
        {plausibleDomain && (
          <script
            defer
            data-domain={plausibleDomain}
            src="https://plausible.io/js/script.js"
          />
        )}
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
