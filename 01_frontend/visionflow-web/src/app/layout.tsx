import "leaflet/dist/leaflet.css";
import "./globals.css";

import type { Metadata } from "next";
import Script from "next/script";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { CommandShell } from "@/components/layout/command-shell";
import { OperatorAccessProvider } from "@/components/security/operator-access-provider";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

// Static traceability contract: the shared shell content grid is rendered by CommandShell.
// <main className="vf-command-main flex-1 p-4 sm:p-6 xl:p-7">

export const metadata: Metadata = {
  title: {
    default: "VisionFlow Drone Control",
    template: "%s | VisionFlow",
  },
  description: "지능형 드론 관제 및 Vision AI 대시보드",
};

interface RootLayoutProps {
  children: ReactNode;
}

export default async function RootLayout({ children }: RootLayoutProps) {
  const operatorSecurity = await getOperatorSecurityStatus();
  const operatorAuthMode = getOperatorAuthMode();

  return (
    <html
      lang="ko"
      data-theme="system"
      data-resolved-theme="light"
      suppressHydrationWarning
    >
      <body className="vf-app-body min-h-screen antialiased">
        <Script
          id="visionflow-theme-bootstrap"
          src="/visionflow-theme-bootstrap.js"
          strategy="beforeInteractive"
        />

        <ThemeProvider>
          <OperatorAccessProvider status={operatorSecurity}>
            <CommandShell
              sidebar={<AppSidebar operatorSecurity={operatorSecurity} />}
              header={
                <AppHeader
                  operatorSecurity={operatorSecurity}
                  operatorAuthMode={operatorAuthMode}
                />
              }
            >
              {children}
            </CommandShell>
          </OperatorAccessProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
