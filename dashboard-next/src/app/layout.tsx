import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { ToastProvider } from "@/components/ui/Toast";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "PULSE — Infrastructure Intelligence",
    template: "%s | PULSE",
  },
  description:
    "AI-powered infrastructure monitoring, observability, and incident response platform. Real-time alerts, anomaly detection, and automated remediation.",
  keywords: [
    "infrastructure monitoring",
    "observability",
    "incident response",
    "APM",
    "uptime monitoring",
    "AI ops",
  ],
  openGraph: {
    type: "website",
    siteName: "PULSE",
    title: "PULSE — Infrastructure Intelligence",
    description:
      "AI-powered infrastructure monitoring, observability, and incident response platform.",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "PULSE" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "PULSE — Infrastructure Intelligence",
    description:
      "AI-powered infrastructure monitoring, observability, and incident response platform.",
    images: ["/og-image.png"],
  },
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
