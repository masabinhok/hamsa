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

const SUMMARY =
  "विपद्‌बारे शंकास्पद पोस्ट पठाउनुहोस्, तथ्य जाँचकर्ताले जाँचेर निर्णय प्रकाशित गर्छन्। " +
  "Send a doubtful post about a disaster in Nepal; fact-checkers check it and publish what they find.";

// Report links are shared in Telegram and Messenger, which preview them from these tags;
// the preview image needs the site's public address, set at build time.
export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: "Hamsa (हंस)",
  description: SUMMARY,
  openGraph: { title: "Hamsa (हंस)", description: SUMMARY, siteName: "Hamsa", type: "website" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${mukta.variable} ${martel.variable}`}>
      <body>{children}</body>
    </html>
  );
}
