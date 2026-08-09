"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type PairingRole = "VIEWER" | "OPERATOR" | "ADMIN";

interface PairingCredentials {
  pairingId: string;
  token: string;
  returnTo: string;
}

interface PairingSnapshot {
  pairingId: string;
  verificationCode: string;
  targetRole: PairingRole;
  status: string;
  deviceName: string | null;
  expiresAt: string;
}

function safeReturnTo(value: string | null): string {
  return value?.startsWith("/") && !value.startsWith("//")
    ? value
    : "/mobile-flight";
}

function bodyMessage(value: unknown, fallback: string): string {
  return typeof value === "object" &&
    value !== null &&
    "message" in value &&
    typeof value.message === "string"
    ? value.message
    : fallback;
}

function bodyCode(value: unknown): string {
  return typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof value.code === "string"
    ? value.code
    : "";
}

function suggestedDeviceName(): string {
  const userAgent = navigator.userAgent;

  if (/Android/i.test(userAgent)) {
    return "Android smartphone";
  }
  if (/iPhone|iPad/i.test(userAgent)) {
    return "Apple mobile";
  }

  return "VisionFlow mobile";
}

export function OperatorPairClient() {
  const router = useRouter();
  const exchangeInFlight = useRef(false);
  const [credentials, setCredentials] =
    useState<PairingCredentials | null>(null);
  const [deviceName, setDeviceName] = useState("VisionFlow mobile");
  const [snapshot, setSnapshot] = useState<PairingSnapshot | null>(null);
  const [claiming, setClaiming] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDeviceName(suggestedDeviceName());

      const params = new URLSearchParams(
        window.location.hash.replace(/^#/, ""),
      );
      const pairingId = params.get("pairingId")?.trim() ?? "";
      const token = params.get("token")?.trim() ?? "";
      const returnTo = safeReturnTo(params.get("returnTo"));

      if (pairingId && token) {
        setCredentials({ pairingId, token, returnTo });
        window.history.replaceState(
          window.history.state,
          "",
          window.location.pathname + window.location.search,
        );
      }
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!credentials || !waiting) {
      return;
    }

    const pairing = credentials;
    let stopped = false;

    async function exchange() {
      if (stopped || exchangeInFlight.current) {
        return;
      }

      exchangeInFlight.current = true;

      try {
        const response = await fetch(
          `/api/operator/pairings/${encodeURIComponent(pairing.pairingId)}/exchange`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              pairingToken: pairing.token,
            }),
            cache: "no-store",
          },
        );
        const body: unknown = await response.json().catch(() => null);

        if (response.ok) {
          stopped = true;
          setWaiting(false);
          router.replace(pairing.returnTo);
          router.refresh();
          return;
        }

        const code = bodyCode(body);

        if (
          response.status === 409 &&
          code === "OPERATOR_PAIRING_APPROVAL_REQUIRED"
        ) {
          return;
        }

        if (
          response.status === 401 ||
          response.status === 404 ||
          response.status === 410
        ) {
          stopped = true;
          setWaiting(false);
          setError(
            bodyMessage(
              body,
              "QR 페어링 요청을 더 이상 사용할 수 없습니다.",
            ),
          );
        }
      } catch {
        // Wi-Fi가 잠깐 흔들리면 다음 polling 주기에서 재시도합니다.
      } finally {
        exchangeInFlight.current = false;
      }
    }

    void exchange();
    const timer = window.setInterval(() => void exchange(), 1_500);

    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [credentials, router, waiting]);

  async function claim() {
    if (!credentials) {
      return;
    }

    setClaiming(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/operator/pairings/${encodeURIComponent(credentials.pairingId)}/claim`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            pairingToken: credentials.token,
            deviceName: deviceName.trim() || "VisionFlow mobile",
          }),
          cache: "no-store",
        },
      );
      const body: unknown = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          bodyMessage(
            body,
            "PC에 QR 페어링 요청을 전달하지 못했습니다.",
          ),
        );
      }

      setSnapshot(body as PairingSnapshot);
      setWaiting(true);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "PC에 QR 페어링 요청을 전달하지 못했습니다.",
      );
    } finally {
      setClaiming(false);
    }
  }

  if (!credentials) {
    return (
      <section className="mx-auto max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-sky-700">
          VisionFlow device pairing
        </p>
        <h1 className="mt-3 text-3xl font-black text-slate-950">
          QR 로그인이 필요합니다
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          PC의 로그인된 VisionFlow 화면에서 모바일 QR을 생성한 뒤
          스마트폰 카메라로 다시 스캔하세요.
        </p>
        <Link
          href="/operator-login"
          className="mt-6 inline-flex rounded-xl border border-slate-300 px-4 py-3 text-sm font-bold text-slate-700"
        >
          비상 KEY 로그인
        </Link>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
      <p className="text-sm font-bold uppercase tracking-[0.18em] text-sky-700">
        Secure device pairing
      </p>
      <h1 className="mt-3 text-3xl font-black text-slate-950">
        스마트폰 연결
      </h1>

      {!snapshot ? (
        <>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            이 기기의 이름만 정한 뒤 PC에 연결 요청을 보냅니다.
            운영자 장기 KEY는 스마트폰으로 전달되지 않습니다.
          </p>

          <label className="mt-6 block text-sm font-bold text-slate-700">
            기기 이름
            <input
              value={deviceName}
              onChange={(event) => setDeviceName(event.target.value)}
              maxLength={80}
              disabled={claiming}
              className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3"
            />
          </label>

          <button
            type="button"
            onClick={() => void claim()}
            disabled={claiming}
            className="mt-5 w-full rounded-xl bg-slate-950 px-4 py-3 font-bold text-white disabled:opacity-50"
          >
            {claiming ? "연결 요청 중..." : "PC에 연결 요청"}
          </button>
        </>
      ) : (
        <>
          <div className="mt-6 rounded-2xl border border-sky-200 bg-sky-50 p-5 text-center">
            <p className="text-sm font-bold text-sky-800">
              PC 화면과 같은 숫자인지 확인하세요
            </p>
            <p className="mt-3 font-mono text-4xl font-black tracking-[0.25em] text-slate-950">
              {snapshot.verificationCode}
            </p>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="font-semibold text-slate-500">요청 역할</dt>
              <dd className="mt-1 font-black text-slate-900">
                {snapshot.targetRole}
              </dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="font-semibold text-slate-500">기기</dt>
              <dd className="mt-1 font-black text-slate-900">
                {snapshot.deviceName ?? deviceName}
              </dd>
            </div>
          </dl>

          <p className="mt-5 rounded-xl bg-amber-50 p-4 text-sm font-semibold text-amber-900">
            {waiting
              ? "PC에서 이 기기를 승인해 주세요. 승인되면 자동으로 로그인됩니다."
              : "페어링 상태를 확인하고 있습니다."}
          </p>
        </>
      )}

      {error && (
        <div
          role="alert"
          className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700"
        >
          {error}
        </div>
      )}
    </section>
  );
}
