"use client";

import QRCode from "qrcode";
import { useEffect, useMemo, useRef, useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import type { MobileHttpsRuntimeProfile } from "@/types/mobile-https-runtime";

type PairingRole = "VIEWER" | "OPERATOR" | "ADMIN";
type PairingStatus =
  | "PENDING"
  | "CLAIMED"
  | "APPROVED"
  | "CONSUMED"
  | "CANCELLED"
  | "EXPIRED";

interface PairingCreation {
  pairingId: string;
  pairingToken: string;
  verificationCode: string;
  targetRole: PairingRole;
  status: PairingStatus;
  expiresAt: string;
}

interface PairingSnapshot {
  pairingId: string;
  verificationCode: string;
  targetRole: PairingRole;
  status: PairingStatus;
  deviceName: string | null;
  createdAt: string;
  claimedAt: string | null;
  approvedAt: string | null;
  expiresAt: string;
}

const ROLE_RANK: Record<PairingRole, number> = {
  VIEWER: 1,
  OPERATOR: 2,
  ADMIN: 3,
};

function isPairingRole(value: unknown): value is PairingRole {
  return value === "VIEWER" || value === "OPERATOR" || value === "ADMIN";
}

function bodyMessage(value: unknown, fallback: string): string {
  return typeof value === "object" &&
    value !== null &&
    "message" in value &&
    typeof value.message === "string"
    ? value.message
    : fallback;
}

async function loadMobileHttpsRuntime(): Promise<MobileHttpsRuntimeProfile | null> {
  const response = await fetch("/api/mobile/runtime-network", {
    cache: "no-store",
  });
  const body: unknown = await response.json().catch(() => null);

  if (!response.ok || typeof body !== "object" || body === null) {
    return null;
  }

  return body as MobileHttpsRuntimeProfile;
}

function normalizeMobileOrigin(value: string): string {
  const candidate = value.trim();

  if (!candidate) {
    throw new Error(
      "스마트폰 접속용 HTTPS 주소를 직접 입력하세요. 예: https://192.168.10.108:3443",
    );
  }

  let parsed: URL;

  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error(
      "스마트폰 접속 주소 형식이 올바르지 않습니다. 예: https://192.168.10.108:3443",
    );
  }

  if (parsed.protocol !== "https:") {
    throw new Error("스마트폰 접속 주소는 https:// 주소여야 합니다.");
  }
  if (
    parsed.hostname === "localhost" ||
    parsed.hostname === "127.0.0.1" ||
    parsed.hostname === "::1"
  ) {
    throw new Error(
      "QR에는 localhost를 사용할 수 없습니다. PC의 현재 LAN HTTPS 주소를 입력하세요.",
    );
  }
  if (parsed.username || parsed.password) {
    throw new Error("스마트폰 접속 주소에 사용자 정보를 포함할 수 없습니다.");
  }

  return parsed.origin;
}

export function OperatorPairingConsole() {
  const { status } = useOperatorAccess();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [mobileOrigin, setMobileOrigin] = useState("");
  const [targetRole, setTargetRole] = useState<PairingRole>("OPERATOR");
  const [returnTo, setReturnTo] = useState("/mobile-flight");
  const [creation, setCreation] = useState<PairingCreation | null>(null);
  const [snapshot, setSnapshot] = useState<PairingSnapshot | null>(null);
  const [pairingUrl, setPairingUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runtimeProfile, setRuntimeProfile] =
    useState<MobileHttpsRuntimeProfile | null>(null);
  const [runtimeLoading, setRuntimeLoading] = useState(false);
  const [mobileOriginManual, setMobileOriginManual] = useState(false);
  const issuerRole = isPairingRole(status?.role) ? status.role : null;

  const allowedRoles = useMemo<PairingRole[]>(() => {
    if (!issuerRole) {
      return [];
    }

    return (["VIEWER", "OPERATOR", "ADMIN"] as PairingRole[]).filter(
      (role) => ROLE_RANK[role] <= ROLE_RANK[issuerRole],
    );
  }, [issuerRole]);

  useEffect(() => {
    let cancelled = false;

    const timer = window.setTimeout(() => {
      const currentHost = window.location.hostname;
      const currentIsLan =
        currentHost !== "localhost" &&
        currentHost !== "127.0.0.1" &&
        currentHost !== "::1";
      const remembered =
        window.localStorage.getItem("visionflow.mobilePairingOrigin") ?? "";

      if (issuerRole === "VIEWER") {
        setTargetRole("VIEWER");
      } else if (issuerRole === "OPERATOR") {
        setTargetRole("OPERATOR");
      } else if (issuerRole === "ADMIN") {
        setTargetRole("OPERATOR");
      }

      async function initializeMobileOrigin() {
        setRuntimeLoading(true);

        try {
          const profile = await loadMobileHttpsRuntime();
          if (cancelled) {
            return;
          }

          setRuntimeProfile(profile);

          if (profile?.origin) {
            setMobileOrigin(profile.origin);
            setMobileOriginManual(false);
            return;
          }

          if (currentIsLan && window.location.protocol === "https:") {
            setMobileOrigin(window.location.origin);
            setMobileOriginManual(false);
            return;
          }

          setMobileOrigin(remembered);
          setMobileOriginManual(Boolean(remembered));
        } finally {
          if (!cancelled) {
            setRuntimeLoading(false);
          }
        }
      }

      void initializeMobileOrigin();
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [issuerRole]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pairingUrl) {
      return;
    }

    void QRCode.toCanvas(canvas, pairingUrl, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 280,
    }).catch(() => {
      setError("QR 코드를 그리지 못했습니다. 연결 주소를 복사해 사용하세요.");
    });
  }, [pairingUrl]);

  useEffect(() => {
    if (!creation) {
      return;
    }

    const pairing = creation;
    let stopped = false;
    let inFlight = false;

    async function refresh() {
      if (stopped || inFlight) {
        return;
      }

      inFlight = true;
      try {
        const response = await fetch(
          `/api/operator/pairings/${encodeURIComponent(pairing.pairingId)}`,
          { cache: "no-store" },
        );
        const body: unknown = await response.json().catch(() => null);

        if (!response.ok) {
          if (response.status === 404 || response.status === 410) {
            setError(bodyMessage(body, "QR 페어링 요청이 만료되었습니다."));
            stopped = true;
          }
          return;
        }

        const next = body as PairingSnapshot;
        setSnapshot(next);

        if (
          next.status === "CONSUMED" ||
          next.status === "CANCELLED" ||
          next.status === "EXPIRED"
        ) {
          stopped = true;
        }
      } finally {
        inFlight = false;
      }
    }

    void refresh();
    const timer = window.setInterval(() => void refresh(), 1_500);

    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [creation]);

  async function refreshMobileOrigin() {
    setRuntimeLoading(true);
    setError(null);

    try {
      const profile = await loadMobileHttpsRuntime();
      setRuntimeProfile(profile);

      if (!profile) {
        throw new Error(
          "Windows host 자동 감지 정보를 읽지 못했습니다. Runtime Agent가 실행 중인지 확인하세요.",
        );
      }

      if (profile.origin) {
        setMobileOrigin(profile.origin);
        setMobileOriginManual(false);
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "스마트폰 HTTPS 주소를 다시 감지하지 못했습니다.",
      );
    } finally {
      setRuntimeLoading(false);
    }
  }

  async function createPairing() {
    if (!issuerRole || !allowedRoles.includes(targetRole)) {
      setError("현재 역할에서 발급할 수 없는 모바일 권한입니다.");
      return;
    }

    setBusy(true);
    setError(null);
    setSnapshot(null);

    try {
      const origin = normalizeMobileOrigin(mobileOrigin);
      const usingDetectedOrigin =
        !mobileOriginManual && runtimeProfile?.origin === origin;

      if (usingDetectedOrigin && !runtimeProfile.ready) {
        throw new Error(runtimeProfile.message);
      }

      window.localStorage.setItem("visionflow.mobilePairingOrigin", origin);

      const response = await fetch("/api/operator/pairings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetRole }),
        cache: "no-store",
      });
      const body: unknown = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          bodyMessage(body, "QR 페어링 요청을 생성하지 못했습니다."),
        );
      }

      const next = body as PairingCreation;
      const url = new URL("/operator-pair", origin);

      url.hash = new URLSearchParams({
        pairingId: next.pairingId,
        token: next.pairingToken,
        returnTo,
      }).toString();

      setCreation(next);
      setSnapshot({
        pairingId: next.pairingId,
        verificationCode: next.verificationCode,
        targetRole: next.targetRole,
        status: next.status,
        deviceName: null,
        createdAt: new Date().toISOString(),
        claimedAt: null,
        approvedAt: null,
        expiresAt: next.expiresAt,
      });
      setPairingUrl(url.toString());
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "QR 페어링 요청을 생성하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function approvePairing() {
    if (!creation || snapshot?.status !== "CLAIMED") {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/operator/pairings/${encodeURIComponent(creation.pairingId)}/approve`,
        {
          method: "POST",
          cache: "no-store",
        },
      );
      const body: unknown = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(bodyMessage(body, "QR 페어링을 승인하지 못했습니다."));
      }

      setSnapshot(body as PairingSnapshot);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "QR 페어링을 승인하지 못했습니다.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancelPairing() {
    if (!creation) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await fetch(
        `/api/operator/pairings/${encodeURIComponent(creation.pairingId)}`,
        {
          method: "DELETE",
          cache: "no-store",
        },
      );
    } finally {
      setCreation(null);
      setSnapshot(null);
      setPairingUrl("");
      setBusy(false);
    }
  }

  async function copyPairingUrl() {
    if (!pairingUrl) {
      return;
    }

    await navigator.clipboard.writeText(pairingUrl);
  }

  const remainingLabel = creation
    ? new Date(creation.expiresAt).toLocaleTimeString("ko-KR")
    : null;
  const detectedOriginBlocked =
    !mobileOriginManual &&
    runtimeProfile?.origin === mobileOrigin.trim() &&
    !runtimeProfile.ready;
  const runtimeTone = mobileOriginManual
    ? "border-amber-200 bg-amber-50 text-amber-800"
    : runtimeProfile?.ready
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : runtimeProfile?.state === "BLOCKED"
        ? "border-red-200 bg-red-50 text-red-800"
        : runtimeProfile?.state === "STALE"
          ? "border-amber-200 bg-amber-50 text-amber-800"
          : "border-slate-200 bg-slate-50 text-slate-600";
  const runtimeLabel = mobileOriginManual
    ? "수동 주소"
    : runtimeLoading
      ? "주소 감지 중"
      : runtimeProfile?.ready
        ? "자동 감지됨 · HTTPS 정상"
        : runtimeProfile?.state === "BLOCKED"
          ? "자동 감지됨 · HTTPS 확인 필요"
          : runtimeProfile?.state === "STALE"
            ? "자동 감지 정보 만료"
            : "자동 감지 대기";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-sky-700">
          Secure device pairing
        </p>
        <h1 className="mt-2 text-3xl font-black text-slate-950">
          스마트폰 QR 로그인
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
          장기 운영자 KEY는 QR에 넣지 않습니다. 5분짜리 일회용 토큰을
          스마트폰이 요청하고, 이 PC에서 확인 코드를 대조한 뒤 승인하면
          스마트폰 전용 HttpOnly 세션이 새로 발급됩니다.
        </p>
      </header>

      <section className="grid gap-5 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm lg:grid-cols-2">
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="block text-sm font-bold text-slate-700">
              스마트폰 접속용 HTTPS 주소
              <input
                value={mobileOrigin}
                onChange={(event) => {
                  setMobileOrigin(event.target.value);
                  setMobileOriginManual(true);
                }}
                disabled={Boolean(creation)}
                placeholder="예: https://192.168.10.108:3443"
                required
                aria-describedby="mobile-pairing-origin-help"
                className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono text-sm"
              />
            </label>

            <div className={`rounded-xl border p-3 text-xs ${runtimeTone}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-black">{runtimeLabel}</p>
                  <p className="mt-1 leading-5">
                    {mobileOriginManual
                      ? "직접 입력한 주소입니다. 자동 SAN/HTTPS 검증 결과는 적용되지 않습니다."
                      : runtimeProfile?.message ??
                        "Windows host Runtime Agent의 네트워크 정보를 기다리고 있습니다."}
                  </p>
                </div>
                {!creation && (
                  <button
                    type="button"
                    onClick={() => void refreshMobileOrigin()}
                    disabled={runtimeLoading}
                    className="shrink-0 rounded-lg border border-current/20 bg-white/70 px-3 py-2 font-bold disabled:opacity-50"
                  >
                    {runtimeLoading ? "감지 중..." : "주소 다시 감지"}
                  </button>
                )}
              </div>
              {runtimeProfile?.hostIp && !mobileOriginManual && (
                <p className="mt-2 font-mono">
                  Host {runtimeProfile.hostIp} · Port {runtimeProfile.port}
                </p>
              )}
            </div>

            <p
              id="mobile-pairing-origin-help"
              className="text-xs leading-5 text-slate-500"
            >
              자동 감지 주소는 인증서 SAN과 HTTPS /healthz까지 확인합니다. 필요하면 입력창을 직접 수정해 수동 override할 수 있습니다.
            </p>
          </div>

          <label className="block text-sm font-bold text-slate-700">
            스마트폰에 부여할 역할
            <select
              value={targetRole}
              onChange={(event) =>
                setTargetRole(event.target.value as PairingRole)
              }
              disabled={Boolean(creation)}
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3"
            >
              {allowedRoles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-bold text-slate-700">
            로그인 후 이동
            <select
              value={returnTo}
              onChange={(event) => setReturnTo(event.target.value)}
              disabled={Boolean(creation)}
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3"
            >
              <option value="/mobile-flight">통합 비행</option>
              <option value="/mobile-control">가상 드론 송신기</option>
              <option value="/dashboard">운영 대시보드</option>
            </select>
          </label>

          {!creation ? (
            <button
              type="button"
              onClick={() => void createPairing()}
              disabled={
                busy ||
                !issuerRole ||
                runtimeLoading ||
                detectedOriginBlocked
              }
              className="w-full rounded-xl bg-slate-950 px-4 py-3 font-bold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? "QR 생성 중..." : "5분 일회용 QR 생성"}
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void copyPairingUrl()}
                className="flex-1 rounded-xl border border-slate-300 px-4 py-3 text-sm font-bold"
              >
                연결 주소 복사
              </button>
              <button
                type="button"
                onClick={() => void cancelPairing()}
                disabled={busy}
                className="rounded-xl border border-red-200 px-4 py-3 text-sm font-bold text-red-700"
              >
                취소
              </button>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700"
            >
              {error}
            </div>
          )}
        </div>

        <div className="flex min-h-80 flex-col items-center justify-center rounded-2xl bg-slate-50 p-5 text-center">
          {creation ? (
            <>
              <canvas
                ref={canvasRef}
                width={280}
                height={280}
                aria-label="스마트폰 로그인 QR 코드"
                className="rounded-xl bg-white p-2 shadow-sm"
              />
              <p className="mt-4 text-xs font-semibold text-slate-500">
                QR 만료 시각 {remainingLabel}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                QR에는 장기 KEY가 아닌 일회용 토큰만 포함됩니다.
              </p>
            </>
          ) : (
            <div className="space-y-2 text-sm leading-6 text-slate-500">
              <p>
                QR 생성 전에 Windows host의 현재 LAN 주소와
                <br />
                mobile HTTPS 상태를 자동으로 확인합니다.
              </p>
              {runtimeProfile?.origin && !mobileOriginManual && (
                <p className="font-mono text-xs text-slate-600">
                  {runtimeProfile.origin}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {creation && snapshot && (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs font-bold text-slate-500">상태</p>
              <p className="mt-1 text-lg font-black text-slate-950">
                {snapshot.status}
              </p>
            </div>
            <div>
              <p className="text-xs font-bold text-slate-500">대상 역할</p>
              <p className="mt-1 text-lg font-black text-slate-950">
                {snapshot.targetRole}
              </p>
            </div>
            <div>
              <p className="text-xs font-bold text-slate-500">요청 기기</p>
              <p className="mt-1 text-lg font-black text-slate-950">
                {snapshot.deviceName ?? "QR 스캔 대기"}
              </p>
            </div>
          </div>

          {(snapshot.status === "CLAIMED" ||
            snapshot.status === "APPROVED") && (
            <div className="mt-6 rounded-2xl border border-sky-200 bg-sky-50 p-5 text-center">
              <p className="text-sm font-bold text-sky-800">
                스마트폰과 같은 숫자인지 확인
              </p>
              <p className="mt-2 font-mono text-4xl font-black tracking-[0.25em] text-slate-950">
                {snapshot.verificationCode}
              </p>
            </div>
          )}

          {snapshot.status === "CLAIMED" && (
            <button
              type="button"
              onClick={() => void approvePairing()}
              disabled={busy}
              className="mt-5 w-full rounded-xl bg-emerald-700 px-4 py-3 font-bold text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {busy
                ? "승인 중..."
                : `${snapshot.deviceName ?? "이 기기"}를 ${snapshot.targetRole}로 승인`}
            </button>
          )}

          {snapshot.status === "APPROVED" && (
            <p className="mt-5 rounded-xl bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">
              승인 완료. 스마트폰이 새 세션을 교환하는 중입니다.
            </p>
          )}

          {snapshot.status === "CONSUMED" && (
            <p className="mt-5 rounded-xl bg-slate-100 p-4 text-sm font-semibold text-slate-700">
              스마트폰 로그인 완료. 이 QR은 재사용할 수 없습니다.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
