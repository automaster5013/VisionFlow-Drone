"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

interface OperatorLoginFormProps {
  returnTo: string;
}

const MIN_OPERATOR_KEY_LENGTH = 24;
const MAX_OPERATOR_KEY_LENGTH = 4096;

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
    return `${Math.ceil(seconds)}초 후`;
  }

  const retryAt = new Date(value).getTime();
  if (Number.isFinite(retryAt) && retryAt > Date.now()) {
    const remainingSeconds = Math.ceil((retryAt - Date.now()) / 1_000);
    return `${remainingSeconds}초 후`;
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
      ? `로그인 시도가 일시적으로 잠겼습니다. ${retryLabel} 다시 시도하세요.`
      : "로그인 시도가 일시적으로 잠겼습니다. 잠시 후 다시 시도하세요.";
  }
  if (status === 401) {
    return "운영자 인증 키가 일치하지 않습니다. 저장된 로그인 정보를 선택하지 말고 현재 키를 다시 붙여넣으세요.";
  }
  if (status === 400) {
    return "운영자 인증 키 형식이 올바르지 않습니다. 현재 키를 다시 붙여넣으세요.";
  }
  if (status === 403) {
    return "현재 주소에서는 로그인을 요청할 수 없습니다. 같은 HTTPS 화면에서 다시 시도하세요.";
  }
  if (status === 409) {
    return "브라우저 세션 로그인 모드가 활성화되지 않았습니다.";
  }
  if (status === 503) {
    return "백엔드 운영자 로그인 서비스에 연결할 수 없습니다.";
  }
  return messageFromBody(body) ?? "운영자 로그인에 실패했습니다.";
}

export function OperatorLoginForm({ returnTo }: OperatorLoginFormProps) {
  const router = useRouter();
  const [operatorKey, setOperatorKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const normalizedKey = operatorKey.trim();
  const keyLength = normalizedKey.length;
  const keyLengthIsValid =
    keyLength >= MIN_OPERATOR_KEY_LENGTH &&
    keyLength <= MAX_OPERATOR_KEY_LENGTH;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!normalizedKey) {
      setError("운영자 인증 키를 입력하세요.");
      return;
    }
    if (!keyLengthIsValid) {
      setError(
        `운영자 인증 키 길이를 확인하세요. 현재 ${keyLength}자가 입력되었습니다.`,
      );
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/operator/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operatorKey: normalizedKey }),
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

      setOperatorKey("");
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
      autoComplete="off"
      className="mt-6 space-y-5"
      aria-busy={submitting}
    >
      <div>
        <div className="flex items-center justify-between gap-3">
          <label
            htmlFor="visionflow-operator-access-key"
            className="text-sm font-semibold text-slate-700"
          >
            운영자 인증 키
          </label>
          <button
            type="button"
            onClick={() => {
              setOperatorKey("");
              setError(null);
            }}
            disabled={submitting || operatorKey.length === 0}
            className="text-xs font-semibold text-slate-500 hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            입력 지우기
          </button>
        </div>
        <input
          id="visionflow-operator-access-key"
          name="visionflowOperatorAccessKey"
          type="password"
          value={operatorKey}
          onChange={(event) => {
            setOperatorKey(event.currentTarget.value);
            setError(null);
          }}
          autoComplete="new-password"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          inputMode="text"
          maxLength={MAX_OPERATOR_KEY_LENGTH}
          required
          disabled={submitting}
          autoFocus
          aria-describedby="operator-key-input-status"
          aria-invalid={Boolean(error)}
          data-1p-ignore="true"
          data-lpignore="true"
          data-bwignore="true"
          data-form-type="other"
          className="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:opacity-60"
          placeholder="현재 VIEWER / OPERATOR / ADMIN 키 붙여넣기"
        />
        <p
          id="operator-key-input-status"
          className={`mt-2 text-xs font-medium ${
            keyLength === 0
              ? "text-slate-500"
              : keyLengthIsValid
                ? "text-emerald-700"
                : "text-amber-700"
          }`}
          aria-live="polite"
        >
          {keyLength === 0
            ? "저장된 로그인 정보를 선택하지 말고 현재 키를 직접 붙여넣으세요."
            : keyLengthIsValid
              ? `${keyLength}자 입력됨 · 제출 가능한 길이입니다.`
              : `${keyLength}자 입력됨 · 키가 너무 짧습니다.`}
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
        disabled={submitting || !keyLengthIsValid}
        className="w-full rounded-xl bg-slate-950 px-4 py-3 font-bold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? "로그인 확인 중..." : "운영자 로그인"}
      </button>
    </form>
  );
}
