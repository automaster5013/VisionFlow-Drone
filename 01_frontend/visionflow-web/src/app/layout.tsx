import "leaflet/dist/leaflet.css";
import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { OperatorAccessProvider } from "@/components/security/operator-access-provider";
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
      <html lang="ko">
      <body className="min-h-screen bg-slate-100 text-slate-900 antialiased">
      <OperatorAccessProvider status={operatorSecurity}>
        <div className="flex min-h-screen">
          <AppSidebar operatorSecurity={operatorSecurity} />

          <div className="flex min-w-0 flex-1 flex-col">
            <AppHeader
              operatorSecurity={operatorSecurity}
              operatorAuthMode={operatorAuthMode}
            />

            <main className="flex-1 p-5 sm:p-8">{children}</main>
          </div>
        </div>
      </OperatorAccessProvider>
      </body>
      </html>
  );
}
