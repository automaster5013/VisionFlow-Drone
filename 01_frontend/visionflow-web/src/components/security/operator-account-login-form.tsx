"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

interface OperatorAccountLoginFormProps {
  returnTo: string;
}

const MAX_USERNAME_LENGTH = 100;
const MAX_PASSWORD_LENGTH = 4096;

function messageFromBody(body: unknown): string | null {
  if (
    typeof body === "object" &&
    body !== null &&
    "message" in body &&
    typeof body.message === "string" &&
    body.message.trim()
  ) {
    return body.message.trim();
  }
  return null;
}

function retryAfterLabel(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds > 0) {
    return `${Math.ceil(seconds)}초`;
  }
  const retryAt = new Date(value).getTime();
  if (Number.isFinite(retryAt) && retryAt > Date.now()) {
    return `${Math.ceil((retryAt - Date.now()) / 1_000)}초`;
  }
  return null;
}

function loginErrorMessage(
  status: number,
  body: unknown,
  retryAfter: string | null,
): string {
  if (status === 429) {
    const retryLabel = retryAfterLabel(retryAfter);
    return retryLabel
      ? `로그인 시도가 잠시 제한되었습니다. ${retryLabel} 후 다시 시도하세요.`
      : "로그인 시도가 잠시 제한되었습니다. 잠시 후 다시 시도하세요.";
  }
  if (status === 401) {
    return "사용자 ID 또는 비밀번호가 올바르지 않습니다.";
  }
  if (status === 400) {
    return "로그인 정보를 확인하세요.";
  }
  if (status === 403) {
    return "현재 주소에서는 로그인할 수 없습니다. 동일한 VisionFlow 화면에서 다시 시도하세요.";
  }
  if (status === 409) {
    return "브라우저 세션 로그인 모드가 활성화되지 않았습니다.";
  }
  if (status === 503) {
    return "백엔드 로그인 서비스에 연결할 수 없습니다.";
  }
  return messageFromBody(body) ?? "운영자 로그인에 실패했습니다.";
}

export function OperatorAccountLoginForm({
  returnTo,
}: OperatorAccountLoginFormProps) {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalizedUsername = username.trim();
  const canSubmit =
    normalizedUsername.length > 0 &&
    normalizedUsername.length <= MAX_USERNAME_LENGTH &&
    password.length > 0 &&
    password.length <= MAX_PASSWORD_LENGTH;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      setError("사용자 ID와 비밀번호를 입력하세요.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: normalizedUsername,
          password,
        }),
        cache: "no-store",
      });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          loginErrorMessage(
            response.status,
            body,
            response.headers.get("retry-after"),
          ),
        );
      }

      setPassword("");
      const passwordChangeRequired =
        typeof body === "object" &&
        body !== null &&
        "passwordChangeRequired" in body &&
        body.passwordChangeRequired === true;
      router.replace(
        passwordChangeRequired
          ? `/operator-password-change?returnTo=${encodeURIComponent(returnTo)}`
          : returnTo,
      );
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
    <form onSubmit={submit} className="mt-6 space-y-5" aria-busy={submitting}>
      <div>
        <label
          htmlFor="visionflow-operator-username"
          className="text-sm font-semibold text-slate-700"
        >
          사용자 ID
        </label>
        <input
          id="visionflow-operator-username"
          name="username"
          type="text"
          value={username}
          onChange={(event) => {
            setUsername(event.currentTarget.value);
            setError(null);
          }}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          maxLength={MAX_USERNAME_LENGTH}
          required
          disabled={submitting}
          autoFocus
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
          placeholder="예: demo-operator"
        />
      </div>

      <div>
        <label
          htmlFor="visionflow-operator-password"
          className="text-sm font-semibold text-slate-700"
        >
          비밀번호
        </label>
        <input
          id="visionflow-operator-password"
          name="password"
          type="password"
          value={password}
          onChange={(event) => {
            setPassword(event.currentTarget.value);
            setError(null);
          }}
          autoComplete="current-password"
          maxLength={MAX_PASSWORD_LENGTH}
          required
          disabled={submitting}
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
          placeholder="비밀번호를 입력하세요"
        />
        <p className="mt-2 text-xs leading-5 text-slate-500">
          역할은 계정에 지정되어 있으며 로그인 시 서버가 자동으로 적용합니다.
        </p>
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
        {submitting ? "로그인 중..." : "로그인"}
      </button>
    </form>
  );
}
