import "leaflet/dist/leaflet.css";
import "./globals.css";

import type { Metadata } from "next";
import Script from "next/script";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { OperatorAccessProvider } from "@/components/security/operator-access-provider";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { buildThemeBootstrapScript } from "@/lib/theme";
import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

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
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: buildThemeBootstrapScript(),
          }}
        />

        <ThemeProvider>
          <OperatorAccessProvider status={operatorSecurity}>
            <div className="vf-command-shell flex min-h-screen">
              <AppSidebar operatorSecurity={operatorSecurity} />

              <div className="flex min-w-0 flex-1 flex-col">
                <AppHeader
                  operatorSecurity={operatorSecurity}
                  operatorAuthMode={operatorAuthMode}
                />

                <main className="vf-command-main flex-1 p-4 sm:p-6 xl:p-7">
                  {children}
                </main>
              </div>
            </div>
          </OperatorAccessProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
