import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign In",
  description:
    "Sign in to PULSE to monitor your infrastructure, manage incidents, and access real-time observability dashboards.",
  openGraph: {
    title: "Sign In | PULSE",
    description:
      "Sign in to PULSE to monitor your infrastructure, manage incidents, and access real-time observability dashboards.",
  },
  robots: {
    index: false,
    follow: false,
  },
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
