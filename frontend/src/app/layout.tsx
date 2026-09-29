import type { Metadata } from "next";
import localFont from "next/font/local";
import { AuthGate, AuthProvider } from "@/components/AuthProvider";
import { LlmSettingsProvider } from "@/components/LlmSettingsProvider";
import { NavBar } from "@/components/NavBar";
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
  title: "GitMind",
  description:
    "Multi-agent AI code review for GitHub pull requests: security, quality and performance.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body className="min-h-screen">
        <AuthProvider>
          <LlmSettingsProvider>
            <NavBar />
            <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
              <AuthGate>{children}</AuthGate>
            </main>
          </LlmSettingsProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
