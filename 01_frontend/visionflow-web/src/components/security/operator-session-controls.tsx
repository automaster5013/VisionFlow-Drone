"use client";

import Link from "next/link";
import { useState } from "react";

import type {
  OperatorAuthMode,
  OperatorSecurityStatus,
} from "@/types/operator-security";

interface OperatorSessionControlsProps {
  authMode: OperatorAuthMode;
  status: OperatorSecurityStatus | null;
}

export function OperatorSessionControls({
  authMode,
  status,
}: OperatorSessionControlsProps) {
  const [loggingOut, setLoggingOut] = useState(false);

  if (!status?.enabled) {
    return null;
  }

  if (authMode === "static") {
    return (
      <span className="hidden text-[11px] font-semibold text-slate-400 lg:inline">
        STATIC KEY
      </span>
    );
  }

  if (!status.authenticated) {
    return (
      <Link
        href="/operator-login"
        className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-bold text-white hover:bg-slate-800"
      >
        로그인
      </Link>
    );
  }

  async function logout() {
    if (loggingOut) {
      return;
    }
    setLoggingOut(true);
    try {
      await fetch("/api/operator/session", {
        method: "DELETE",
        cache: "no-store",
      });
    } finally {
      window.location.assign("/operator-login");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/operator-pairing"
        className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-bold text-sky-800 hover:bg-sky-100"
      >
        QR 로그인
      </Link>
      <button
        type="button"
        onClick={() => void logout()}
        disabled={loggingOut}
        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {loggingOut ? "로그아웃 중" : "로그아웃"}
      </button>
    </div>
  );
}
