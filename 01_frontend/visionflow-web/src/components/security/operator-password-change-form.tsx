"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

interface OperatorPasswordChangeFormProps {
  returnTo: string;
}

const MIN_PASSWORD_LENGTH = 15;
const MAX_PASSWORD_LENGTH = 128;

function responseMessage(body: unknown): string | null {
  return typeof body === "object" &&
    body !== null &&
    "message" in body &&
    typeof body.message === "string"
    ? body.message
    : null;
}

export function OperatorPasswordChangeForm({
  returnTo,
}: OperatorPasswordChangeFormProps) {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validLength =
    newPassword.length >= MIN_PASSWORD_LENGTH &&
    newPassword.length <= MAX_PASSWORD_LENGTH;
  const matches = newPassword === confirmPassword;
  const canSubmit = validLength && matches;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validLength) {
      setError("새 비밀번호는 15~128자로 입력하세요.");
      return;
    }
    if (!matches) {
      setError("새 비밀번호 확인 값이 일치하지 않습니다.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ newPassword }),
        cache: "no-store",
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          responseMessage(body) ?? "비밀번호를 변경하지 못했습니다.",
        );
      }

      setNewPassword("");
      setConfirmPassword("");
      router.replace(returnTo);
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "비밀번호를 변경하지 못했습니다.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 space-y-5" aria-busy={submitting}>
      <div>
        <label
          htmlFor="visionflow-new-password"
          className="text-sm font-semibold text-slate-700"
        >
          새 비밀번호
        </label>
        <input
          id="visionflow-new-password"
          name="newPassword"
          type="password"
          value={newPassword}
          onChange={(event) => {
            setNewPassword(event.currentTarget.value);
            setError(null);
          }}
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
          required
          disabled={submitting}
          autoFocus
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
        />
        <p className="mt-2 text-xs leading-5 text-slate-500">
          15자 이상으로 설정하세요. 현재 임시 비밀번호는 다시 사용할 수 없습니다.
        </p>
      </div>

      <div>
        <label
          htmlFor="visionflow-confirm-password"
          className="text-sm font-semibold text-slate-700"
        >
          새 비밀번호 확인
        </label>
        <input
          id="visionflow-confirm-password"
          name="confirmPassword"
          type="password"
          value={confirmPassword}
          onChange={(event) => {
            setConfirmPassword(event.currentTarget.value);
            setError(null);
          }}
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={MAX_PASSWORD_LENGTH}
          required
          disabled={submitting}
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700"
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !canSubmit}
        className="w-full rounded-xl bg-slate-950 px-4 py-3 font-bold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "변경 중..." : "새 비밀번호 저장"}
      </button>
    </form>
  );
}
