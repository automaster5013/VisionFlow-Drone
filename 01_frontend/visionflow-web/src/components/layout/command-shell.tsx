"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { PresentationCaptions } from "@/components/layout/presentation-captions";

interface CommandShellProps {
  children: ReactNode;
  header: ReactNode;
  sidebar: ReactNode;
}

export function CommandShell({ children, header, sidebar }: CommandShellProps) {
  const pathname = usePathname();
  const isPublicShowcase = pathname === "/showcase";

  if (isPublicShowcase) {
    return (
      <>
        {children}
        <PresentationCaptions />
      </>
    );
  }

  return (
    <>
      <div className="vf-command-shell flex min-h-screen">
        {sidebar}
        <div className="flex min-w-0 flex-1 flex-col">
          {header}
          <main className="vf-command-main flex-1 p-4 sm:p-6 xl:p-7">{children}</main>
        </div>
      </div>
      <PresentationCaptions />
    </>
  );
}
