"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

interface OperatorLoginFormProps {
  returnTo: string;
}

function extractMessage(body: unknown): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "message" in body &&
    typeof body.message === "string"
  ) {
    return body.message;
  }
  return "운영자 로그인에 실패했습니다.";
}

export function OperatorLoginForm({ returnTo }: OperatorLoginFormProps) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const operatorKey = String(formData.get("operatorKey") ?? "").trim();

    if (!operatorKey) {
      setError("운영자 인증 키를 입력하세요.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operatorKey }),
        cache: "no-store",
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(extractMessage(body));
      }

      form.reset();
      router.replace(returnTo);
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "운영자 로그인에 실패했습니다.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-6 space-y-5"
      aria-busy={submitting}
    >
      <label className="block text-sm font-semibold text-slate-700">
        운영자 인증 키
        <input
          name="operatorKey"
          type="password"
          autoComplete="current-password"
          disabled={submitting}
          autoFocus
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
          placeholder="VIEWER / OPERATOR / ADMIN 키"
        />
      </label>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-slate-950 px-4 py-3 font-bold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "로그인 확인 중..." : "운영자 로그인"}
      </button>
    </form>
  );
}
