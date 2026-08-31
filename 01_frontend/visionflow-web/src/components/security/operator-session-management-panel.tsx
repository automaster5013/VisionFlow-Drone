"use client";

import { useState } from "react";

import { formatKoreanDateTime } from "@/lib/date";
import {
  parseOperatorSessions,
  type OperatorManagedSession,
} from "@/types/operator-session-management";

interface OperatorSessionManagementPanelProps {
  initialSessions: OperatorManagedSession[];
}

function extractMessage(value: unknown, fallback: string): string {
  return typeof value === "object" &&
    value !== null &&
    "message" in value &&
    typeof value.message === "string"
    ? value.message
    : fallback;
}

export function OperatorSessionManagementPanel({
  initialSessions,
}: OperatorSessionManagementPanelProps) {
  const [sessions, setSessions] = useState(initialSessions);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revokingAll, setRevokingAll] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const otherSessionCount = sessions.filter((session) => !session.current).length;

  async function refresh() {
    if (refreshing) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/sessions", {
        method: "GET",
        cache: "no-store",
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          extractMessage(body, "활성 운영자 세션을 조회하지 못했습니다."),
        );
      }
      const refreshed = parseOperatorSessions(body);
      if (!refreshed) {
        throw new Error("활성 운영자 세션 응답 형식이 올바르지 않습니다.");
      }
      setSessions(refreshed);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "활성 운영자 세션을 조회하지 못했습니다.",
      );
    } finally {
      setRefreshing(false);
    }
  }

  async function revoke(session: OperatorManagedSession) {
    if (
      session.current ||
      revokingId ||
      revokingAll ||
      !window.confirm(
        `${session.username} · ${session.role} 세션을 강제로 종료할까요?`,
      )
    ) {
      return;
    }

    setRevokingId(session.sessionId);
    setError(null);
    try {
      const response = await fetch(
        `/api/operator/sessions/${encodeURIComponent(session.sessionId)}`,
        { method: "DELETE", cache: "no-store" },
      );
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          extractMessage(body, "운영자 세션을 종료하지 못했습니다."),
        );
      }
      setSessions((current) =>
        current.filter((item) => item.sessionId !== session.sessionId),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "운영자 세션을 종료하지 못했습니다.",
      );
    } finally {
      setRevokingId(null);
    }
  }

  async function revokeAllOthers() {
    if (
      otherSessionCount === 0 ||
      revokingId ||
      revokingAll ||
      !window.confirm(
        `현재 세션을 제외한 ${otherSessionCount}개 세션을 모두 종료할까요?`,
      )
    ) {
      return;
    }

    setRevokingAll(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/sessions/others", {
        method: "DELETE",
        cache: "no-store",
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          extractMessage(body, "다른 운영자 세션을 일괄 종료하지 못했습니다."),
        );
      }
      setSessions((current) => current.filter((session) => session.current));
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "다른 운영자 세션을 일괄 종료하지 못했습니다.",
      );
    } finally {
      setRevokingAll(false);
    }
  }

  return (
    <section data-operator-session-panel className="vf-session-command__panel overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h2 className="font-bold text-slate-950">활성 세션</h2>
          <p className="mt-1 text-sm text-slate-500">
            총 {sessions.length}개 · 현재 세션은 헤더의 로그아웃 버튼으로 종료합니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void revokeAllOthers()}
            disabled={
              otherSessionCount === 0 || revokingId !== null || revokingAll
            }
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-bold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {revokingAll
              ? "일괄 종료 중"
              : `다른 세션 모두 종료 (${otherSessionCount})`}
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing || revokingAll}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {refreshing ? "조회 중" : "새로고침"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="m-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">운영자</th>
              <th className="px-4 py-3">세션 ID</th>
              <th className="px-4 py-3">발급 / 최근 사용</th>
              <th className="px-4 py-3">유휴 / 절대 만료</th>
              <th className="px-4 py-3">클라이언트</th>
              <th className="px-4 py-3 text-right">관리</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sessions.map((session) => (
              <tr key={session.sessionId} className="align-top hover:bg-slate-50">
                <td className="px-4 py-3">
                  <p className="font-semibold text-slate-900">{session.username}</p>
                  <span className="mt-1 inline-flex rounded-full bg-sky-100 px-2 py-0.5 text-xs font-bold text-sky-800">
                    {session.role}
                  </span>
                  {session.current ? (
                    <span className="ml-2 inline-flex rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-800">
                      CURRENT
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-600">
                  {session.sessionId}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">
                  <p>{formatKoreanDateTime(session.issuedAt)}</p>
                  <p className="mt-1">{formatKoreanDateTime(session.lastSeenAt)}</p>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">
                  <p>{formatKoreanDateTime(session.idleExpiresAt)}</p>
                  <p className="mt-1">{formatKoreanDateTime(session.expiresAt)}</p>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  {session.clientFingerprint}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    type="button"
                    disabled={
                      session.current || revokingId !== null || revokingAll
                    }
                    onClick={() => void revoke(session)}
                    className="rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {revokingId === session.sessionId ? "종료 중" : "강제 종료"}
                  </button>
                </td>
              </tr>
            ))}
            {sessions.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-12 text-center text-slate-500">
                  현재 활성 운영자 세션이 없습니다.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
