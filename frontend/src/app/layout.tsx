import type { Metadata } from "next";
import { Fraunces, Geist } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const geist = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Closest Chemistry",
  description: "Find your next great combination.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geist.variable} ${fraunces.variable} antialiased bg-cream text-ink`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
