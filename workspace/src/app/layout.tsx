import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import AssistantShell from "@/components/layout/AssistantShell";

export const metadata: Metadata = {
  title: "Breakthrough Engine — Dev Workspace",
  description: "Internal development workspace for Breakthrough Engine",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        <Sidebar />
        <AssistantShell>{children}</AssistantShell>
      </body>
    </html>
  );
}
