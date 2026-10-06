import type { Metadata } from "next";
import { Martel, Mukta } from "next/font/google";
import "./globals.css";

const mukta = Mukta({
  variable: "--font-mukta",
  subsets: ["devanagari", "latin"],
  weight: ["400", "500", "600"],
});

// The reading voice: claims and verdicts, often in Devanagari.
const martel = Martel({
  variable: "--font-martel",
  subsets: ["devanagari", "latin"],
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Hamsa",
  description: "Fact-check triage for Nepali disaster misinformation",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${mukta.variable} ${martel.variable}`}>
      <body>{children}</body>
    </html>
  );
}
