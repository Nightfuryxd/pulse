import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Overview",
  description:
    "Infrastructure health at a glance. Monitor nodes, alerts, incidents, and system performance from the PULSE overview dashboard.",
  openGraph: {
    title: "Overview | PULSE",
    description:
      "Infrastructure health at a glance. Monitor nodes, alerts, incidents, and system performance.",
  },
};

export default function OverviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
