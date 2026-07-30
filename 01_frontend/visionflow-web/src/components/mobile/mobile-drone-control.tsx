"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useMobileDroneSensors } from "@/hooks/use-mobile-drone-sensors";
import type {
  MobileSensorSnapshot,
  MobileTelemetryPayload,
} from "@/types/mobile-telemetry";

interface DroneOption {
  id: number;
  droneCode: string;
  name: string;
}

interface ManualTelemetry {
  latitude: number;
  longitude: number;
  altitude: number;
  heading: number;
  pitch: number;
  roll: number;
  groundSpeed: number;
  horizontalAccuracy: number;
  verticalAccuracy: number;
}

const DEFAULT_MANUAL_TELEMETRY: ManualTelemetry = {
  latitude: 37.5665,
  longitude: 126.978,
  altitude: 30,
  heading: 0,
  pitch: 0,
  roll: 0,
  groundSpeed: 0,
  horizontalAccuracy: 5,
  verticalAccuracy: 8,
};

function isDroneOption(value: unknown): value is DroneOption {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<DroneOption>;

  return (
    typeof candidate.id === "number" &&
    Number.isFinite(candidate.id) &&
    typeof candidate.droneCode === "string" &&
    typeof candidate.name === "string"
  );
}

function parseDroneOptions(payload: unknown): DroneOption[] {
  const candidates = Array.isArray(payload)
    ? payload
    : typeof payload === "object" &&
        payload !== null &&
        "data" in payload &&
        Array.isArray((payload as { data?: unknown }).data)
      ? (payload as { data: unknown[] }).data
      : [];

  return candidates.filter(isDroneOption);
}

function optionalNumber(value: number | null): number | undefined {
  return value !== null && Number.isFinite(value) ? value : undefined;
}

function normalizeHeading(value: number): number {
  return ((value % 360) + 360) % 360;
}

function formatSensorValue(
  value: number | null,
  fractionDigits = 2,
): string {
  return value !== null && Number.isFinite(value)
    ? value.toFixed(fractionDigits)
    : "-";
}

export function MobileDroneControl() {
  const {
    snapshot: sensorSnapshot,
    status: sensorStatus,
    orientationMode,
    secureContext,
    error: sensorError,
    warning: sensorWarning,
    start: startSensors,
    stop: stopSensors,
    getSnapshot,
  } = useMobileDroneSensors();
  const [drones, setDrones] = useState<DroneOption[]>([]);
  const [selectedDroneId, setSelectedDroneId] = useState<number | null>(null);
  const [loadingDrones, setLoadingDrones] = useState(true);
  const [manualMode, setManualMode] = useState(false);
  const [manualTelemetry, setManualTelemetry] = useState<ManualTelemetry>(
    DEFAULT_MANUAL_TELEMETRY,
  );
  const [batteryLevel, setBatteryLevel] = useState(100);
  const [deviceId, setDeviceId] = useState("visionflow-phone-001");
  const [transmitting, setTransmitting] = useState(false);
  const [sendCount, setSendCount] = useState(0);
  const [lastSentAt, setLastSentAt] = useState<Date | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const inFlightRef = useRef(false);

  useEffect(() => {
    const abortController = new AbortController();

    async function loadDrones() {
      try {
        const response = await fetch("/api/drones", {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
          cache: "no-store",
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`드론 목록 조회 실패: ${response.status}`);
        }

        const options = parseDroneOptions(await response.json());

        if (abortController.signal.aborted) {
          return;
        }

        setDrones(options);
        setSelectedDroneId((current) => current ?? options[0]?.id ?? null);
      } catch (error) {
        if (!abortController.signal.aborted) {
          setSendError(
            error instanceof Error
              ? error.message
              : "드론 목록을 불러오지 못했습니다.",
          );
        }
      } finally {
        if (!abortController.signal.aborted) {
          setLoadingDrones(false);
        }
      }
    }

    void loadDrones();

    return () => {
      abortController.abort();
    };
  }, []);

  const currentDisplaySnapshot = useMemo<MobileSensorSnapshot>(() => {
    if (!manualMode) {
      return sensorSnapshot;
    }

    return {
      ...manualTelemetry,
      capturedAt: null,
    };
  }, [manualMode, manualTelemetry, sensorSnapshot]);

  const sendTelemetry = useCallback(async () => {
    if (inFlightRef.current || selectedDroneId === null) {
      return;
    }

    const snapshot = manualMode
      ? {
          ...manualTelemetry,
          capturedAt: Date.now(),
        }
      : getSnapshot();

    if (snapshot.latitude === null || snapshot.longitude === null) {
      setSendError("GPS 좌표를 기다리고 있습니다.");
      return;
    }

    const payload: MobileTelemetryPayload = {
      latitude: snapshot.latitude,
      longitude: snapshot.longitude,
      altitude: optionalNumber(snapshot.altitude),
      batteryLevel,
      heading:
        snapshot.heading === null
          ? undefined
          : normalizeHeading(snapshot.heading),
      pitch: optionalNumber(snapshot.pitch),
      roll: optionalNumber(snapshot.roll),
      groundSpeed: optionalNumber(snapshot.groundSpeed),
      horizontalAccuracy: optionalNumber(snapshot.horizontalAccuracy),
      verticalAccuracy: optionalNumber(snapshot.verticalAccuracy),
      telemetrySource: "MOBILE_SENSOR",
      sourceDeviceId: deviceId.trim() || "visionflow-phone",
    };

    inFlightRef.current = true;

    try {
      const response = await fetch(
        `/api/drones/${selectedDroneId}/telemetry`,
        {
          method: "PATCH",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          cache: "no-store",
        },
      );

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(
          `텔레메트리 전송 실패: ${response.status} ${errorBody}`,
        );
      }

      setSendError(null);
      setSendCount((current) => current + 1);
      setLastSentAt(new Date());
    } catch (error) {
      setSendError(
        error instanceof Error
          ? error.message
          : "텔레메트리를 전송하지 못했습니다.",
      );
    } finally {
      inFlightRef.current = false;
    }
  }, [
    batteryLevel,
    deviceId,
    manualMode,
    manualTelemetry,
    selectedDroneId,
    getSnapshot,
  ]);

  useEffect(() => {
    if (!transmitting) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void sendTelemetry();
    }, 1_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [sendTelemetry, transmitting]);

  async function startTransmission() {
    setSendError(null);

    if (!manualMode) {
      const started = await startSensors();

      if (!started) {
        return;
      }
    }

    setTransmitting(true);
  }

  function stopTransmission() {
    setTransmitting(false);
    stopSensors();
  }

  function updateManualField(
    field: keyof ManualTelemetry,
    value: number,
  ) {
    setManualTelemetry((current) => ({
      ...current,
      [field]: value,
    }));
  }

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-6 text-slate-900">
      <div className="mx-auto max-w-3xl space-y-4">
        <header className="rounded-2xl bg-slate-950 p-5 text-white shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-bold tracking-[0.2em] text-sky-400">
                VISIONFLOW DIGITAL TWIN
              </div>
              <h1 className="mt-2 text-2xl font-bold">
                스마트폰 가상 드론 송신기
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                GPS 위치와 기체 방향을 1초 간격으로 관제 서버에 전송합니다.
              </p>
            </div>

            <Link
              href="/drones"
              className="rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold text-white"
            >
              관제 화면
            </Link>
          </div>
        </header>

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-semibold text-slate-700">
              연결할 드론
              <select
                value={selectedDroneId ?? ""}
                onChange={(event) =>
                  setSelectedDroneId(Number(event.target.value))
                }
                disabled={loadingDrones || transmitting}
                className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
              >
                <option value="" disabled>
                  {loadingDrones ? "드론 조회 중" : "드론 선택"}
                </option>
                {drones.map((drone) => (
                  <option key={drone.id} value={drone.id}>
                    {drone.name} · {drone.droneCode}
                  </option>
                ))}
              </select>
            </label>

            <label className="text-sm font-semibold text-slate-700">
              스마트폰 식별값
              <input
                type="text"
                value={deviceId}
                maxLength={100}
                disabled={transmitting}
                onChange={(event) => setDeviceId(event.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-3"
              />
            </label>
          </div>

          <label className="mt-4 block text-sm font-semibold text-slate-700">
            가상 배터리 {batteryLevel}%
            <input
              type="range"
              min={0}
              max={100}
              value={batteryLevel}
              onChange={(event) => setBatteryLevel(Number(event.target.value))}
              className="mt-2 w-full"
            />
          </label>

          <label className="mt-4 flex items-center gap-3 rounded-xl bg-slate-50 p-3 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={manualMode}
              disabled={transmitting}
              onChange={(event) => setManualMode(event.target.checked)}
              className="h-5 w-5"
            />
            PC에서도 확인할 수 있는 수동 센서 테스트 모드
          </label>
        </section>

        {manualMode && (
          <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
            <h2 className="font-bold text-amber-900">수동 센서 값</h2>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {(
                [
                  ["latitude", "위도"],
                  ["longitude", "경도"],
                  ["altitude", "고도(m)"],
                  ["heading", "방위각(°)"],
                  ["pitch", "피치(°)"],
                  ["roll", "롤(°)"],
                  ["groundSpeed", "속도(m/s)"],
                  ["horizontalAccuracy", "수평 정확도(m)"],
                  ["verticalAccuracy", "수직 정확도(m)"],
                ] as const
              ).map(([field, label]) => (
                <label key={field} className="text-xs font-semibold text-slate-700">
                  {label}
                  <input
                    type="number"
                    step="any"
                    value={manualTelemetry[field]}
                    onChange={(event) =>
                      updateManualField(field, Number(event.target.value))
                    }
                    className="mt-1 w-full rounded-lg border border-amber-300 bg-white px-2 py-2"
                  />
                </label>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-bold">센서 상태</h2>
              <div className="mt-1 text-sm text-slate-500">
                {manualMode
                  ? "수동 테스트 값 사용"
                  : `${sensorStatus} · 방향 ${orientationMode}`}
              </div>
            </div>

            <span
              className={`rounded-full px-3 py-1 text-sm font-bold ${
                transmitting
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {transmitting ? "● TRANSMITTING" : "STOPPED"}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <SensorValue
              label="위도"
              value={formatSensorValue(currentDisplaySnapshot.latitude, 7)}
            />
            <SensorValue
              label="경도"
              value={formatSensorValue(currentDisplaySnapshot.longitude, 7)}
            />
            <SensorValue
              label="고도"
              value={`${formatSensorValue(currentDisplaySnapshot.altitude)}m`}
            />
            <SensorValue
              label="방위각"
              value={`${formatSensorValue(currentDisplaySnapshot.heading, 1)}°`}
            />
            <SensorValue
              label="피치 / 롤"
              value={`${formatSensorValue(currentDisplaySnapshot.pitch, 1)}° / ${formatSensorValue(currentDisplaySnapshot.roll, 1)}°`}
            />
            <SensorValue
              label="속도"
              value={`${formatSensorValue(currentDisplaySnapshot.groundSpeed)}m/s`}
            />
          </div>

          {secureContext === false && !manualMode && (
            <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm font-semibold text-red-800">
              현재 페이지는 HTTPS 보안 연결이 아닙니다. 스마트폰 실센서 모드를 사용하려면 HTTPS로 실행하세요.
            </div>
          )}

          {sensorWarning && !manualMode && (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              {sensorWarning}
            </div>
          )}

          {(sensorError || sendError) && (
            <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {sensorError ?? sendError}
            </div>
          )}

          <div className="mt-5 grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => void startTransmission()}
              disabled={transmitting || selectedDroneId === null}
              className="rounded-xl bg-sky-600 px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              송신 시작
            </button>

            <button
              type="button"
              onClick={stopTransmission}
              disabled={!transmitting}
              className="rounded-xl bg-slate-900 px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              송신 중지
            </button>
          </div>

          <div className="mt-4 text-center text-xs text-slate-500">
            전송 {sendCount}회 · 마지막 성공 {lastSentAt?.toLocaleTimeString("ko-KR") ?? "-"}
          </div>
        </section>
      </div>
    </main>
  );
}

function SensorValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 font-bold text-slate-900">{value}</div>
    </div>
  );
}
