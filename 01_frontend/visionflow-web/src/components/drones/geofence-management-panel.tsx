"use client";

import { useState, type Dispatch, type SetStateAction } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import type { Geofence, GeofenceDraft, GeofenceRule } from "@/types/geofence";

interface GeofenceManagementPanelProps {
  geofences: Geofence[];
  draft: GeofenceDraft | null;
  onDraftChange: Dispatch<SetStateAction<GeofenceDraft | null>>;
  onRefresh: () => Promise<void>;
}

function createEmptyDraft(): GeofenceDraft {
  return {
    id: null,
    name: "",
    ruleType: "KEEP_OUT",
    centerLatitude: null,
    centerLongitude: null,
    radiusMeters: 300,
  };
}

function geofenceToDraft(geofence: Geofence): GeofenceDraft {
  return {
    id: geofence.id,
    name: geofence.name,
    ruleType: geofence.ruleType,
    centerLatitude: Number(geofence.centerLatitude),
    centerLongitude: Number(geofence.centerLongitude),
    radiusMeters: Number(geofence.radiusMeters),
  };
}

async function readErrorMessage(response: Response): Promise<string> {
  const body = await response.text();

  if (!body) {
    return `요청 실패: ${response.status}`;
  }

  try {
    const payload = JSON.parse(body) as {
      message?: unknown;
    };

    if (typeof payload.message === "string") {
      return payload.message;
    }
  } catch {
    // JSON이 아니면 원문을 오류 메시지로 사용합니다.
  }

  return body;
}

export function GeofenceManagementPanel({
  geofences,
  draft,
  onDraftChange,
  onRefresh,
}: GeofenceManagementPanelProps) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const { canOperate, operateDeniedReason } = useOperatorAccess();

  function patchDraft(patch: Partial<GeofenceDraft>) {
    onDraftChange((current) =>
      current
        ? {
            ...current,
            ...patch,
          }
        : current,
    );
  }

  function beginCreate() {
    if (!canOperate) {
      setErrorMessage(operateDeniedReason);
      return;
    }

    setErrorMessage(null);
    setSuccessMessage(null);
    onDraftChange(createEmptyDraft());
  }

  function beginEdit(geofence: Geofence) {
    if (!canOperate) {
      setErrorMessage(operateDeniedReason);
      return;
    }

    setErrorMessage(null);
    setSuccessMessage(null);
    onDraftChange(geofenceToDraft(geofence));
  }

  async function saveDraft() {
    if (!canOperate) {
      setErrorMessage(operateDeniedReason);
      return;
    }

    if (!draft) {
      return;
    }

    const normalizedName = draft.name.trim();

    if (!normalizedName) {
      setErrorMessage("지오펜스 이름을 입력해주세요.");
      return;
    }

    if (
      draft.centerLatitude === null ||
      !Number.isFinite(draft.centerLatitude) ||
      draft.centerLatitude < -90 ||
      draft.centerLatitude > 90
    ) {
      setErrorMessage("올바른 중심 위도를 지정해주세요.");
      return;
    }

    if (
      draft.centerLongitude === null ||
      !Number.isFinite(draft.centerLongitude) ||
      draft.centerLongitude < -180 ||
      draft.centerLongitude > 180
    ) {
      setErrorMessage("올바른 중심 경도를 지정해주세요.");
      return;
    }

    if (
      !Number.isFinite(draft.radiusMeters) ||
      draft.radiusMeters < 1 ||
      draft.radiusMeters > 50_000
    ) {
      setErrorMessage("반경은 1~50,000m 사이여야 합니다.");
      return;
    }

    const editing = draft.id !== null;
    const busy = editing ? `save-${draft.id}` : "create";

    setBusyKey(busy);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await fetch(
        editing ? `/api/geofences/${draft.id}` : "/api/geofences",
        {
          method: editing ? "PUT" : "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: normalizedName,
            ruleType: draft.ruleType,
            centerLatitude: draft.centerLatitude,
            centerLongitude: draft.centerLongitude,
            radiusMeters: draft.radiusMeters,
            ...(editing ? {} : { active: true }),
          }),
        },
      );

      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      await onRefresh();
      onDraftChange(null);
      setSuccessMessage(
        editing ? "지오펜스가 수정되었습니다." : "지오펜스가 생성되었습니다.",
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "지오펜스를 저장하지 못했습니다.",
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function changeActive(geofence: Geofence) {
    if (!canOperate) {
      setErrorMessage(operateDeniedReason);
      return;
    }

    const busy = `active-${geofence.id}`;

    setBusyKey(busy);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await fetch(`/api/geofences/${geofence.id}/active`, {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          active: !geofence.active,
        }),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      await onRefresh();

      if (draft?.id === geofence.id && geofence.active) {
        onDraftChange(null);
      }

      setSuccessMessage(
        geofence.active
          ? "지오펜스가 비활성화되었습니다."
          : "지오펜스가 활성화되었습니다.",
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "활성 상태를 변경하지 못했습니다.",
      );
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-slate-900">지오펜스 관리</h2>
          <p className="mt-1 text-sm text-slate-500">
            지도를 클릭해 중심점을 지정하고 반경과 운용 규칙을 설정합니다.
          </p>
        </div>

        <button
          type="button"
          onClick={draft ? () => onDraftChange(null) : beginCreate}
          disabled={busyKey !== null || (!draft && !canOperate)}
          title={!draft && !canOperate ? operateDeniedReason ?? undefined : undefined}
          className={`rounded-lg px-4 py-2 text-sm font-semibold ${
            draft
              ? "border border-slate-300 text-slate-700"
              : "bg-slate-900 text-white"
          } disabled:cursor-not-allowed disabled:opacity-50`}
        >
          {draft ? "편집 취소" : "새 지오펜스"}
        </button>
      </div>

      {errorMessage && (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          {errorMessage}
        </div>
      )}

      {successMessage && (
        <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
          {successMessage}
        </div>
      )}

      {draft && (
        <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4">
          <div className="mb-4">
            <div className="font-semibold text-amber-900">
              {draft.id === null ? "새 지오펜스" : "지오펜스 수정"}
            </div>
            <div className="mt-1 text-sm text-amber-700">
              편집 중에는 지도 커서가 십자 모양으로 바뀝니다. 원하는 위치를
              클릭하면 중심 좌표가 갱신됩니다.
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <label className="space-y-1 xl:col-span-2">
              <span className="text-xs font-semibold text-slate-700">이름</span>
              <input
                value={draft.name}
                onChange={(event) => patchDraft({ name: event.target.value })}
                maxLength={100}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
                placeholder="예: 서울광장 비행금지구역"
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-700">규칙</span>
              <select
                value={draft.ruleType}
                onChange={(event) =>
                  patchDraft({
                    ruleType: event.target.value as GeofenceRule,
                  })
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
              >
                <option value="KEEP_OUT">진입 금지</option>
                <option value="KEEP_IN">이탈 금지</option>
              </select>
            </label>

            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-700">
                반경(m)
              </span>
              <input
                type="number"
                min={1}
                max={50_000}
                step={10}
                value={draft.radiusMeters}
                onChange={(event) =>
                  patchDraft({ radiusMeters: Number(event.target.value) })
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
            </label>

            <div className="flex items-end">
              <button
                type="button"
                onClick={() => void saveDraft()}
                disabled={busyKey !== null || !canOperate}
                title={canOperate ? undefined : operateDeniedReason ?? undefined}
                className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busyKey?.startsWith("save-") || busyKey === "create"
                  ? "저장 중..."
                  : "저장"}
              </button>
            </div>
          </div>

          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-700">
                중심 위도
              </span>
              <input
                type="number"
                step="0.0000001"
                value={draft.centerLatitude ?? ""}
                onChange={(event) =>
                  patchDraft({
                    centerLatitude:
                      event.target.value === ""
                        ? null
                        : Number(event.target.value),
                  })
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
                placeholder="지도를 클릭하세요"
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs font-semibold text-slate-700">
                중심 경도
              </span>
              <input
                type="number"
                step="0.0000001"
                value={draft.centerLongitude ?? ""}
                onChange={(event) =>
                  patchDraft({
                    centerLongitude:
                      event.target.value === ""
                        ? null
                        : Number(event.target.value),
                  })
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500"
                placeholder="지도를 클릭하세요"
              />
            </label>
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-2 lg:grid-cols-2">
        {geofences.map((geofence) => (
          <div
            key={geofence.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 p-3"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-900">
                  {geofence.name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                    geofence.active
                      ? "bg-emerald-100 text-emerald-700"
                      : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {geofence.active ? "활성" : "비활성"}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {geofence.ruleType === "KEEP_OUT" ? "진입 금지" : "이탈 금지"}
                {" · 반경 "}
                {Math.round(Number(geofence.radiusMeters))}m
              </div>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => beginEdit(geofence)}
                disabled={busyKey !== null || !canOperate}
                title={canOperate ? undefined : operateDeniedReason ?? undefined}
                className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
              >
                수정
              </button>
              <button
                type="button"
                onClick={() => void changeActive(geofence)}
                disabled={busyKey !== null || !canOperate}
                title={canOperate ? undefined : operateDeniedReason ?? undefined}
                className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                  geofence.active
                    ? "bg-slate-100 text-slate-700"
                    : "bg-emerald-600 text-white"
                } disabled:opacity-50`}
              >
                {busyKey === `active-${geofence.id}`
                  ? "변경 중..."
                  : geofence.active
                    ? "비활성화"
                    : "활성화"}
              </button>
            </div>
          </div>
        ))}

        {geofences.length === 0 && (
          <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500 lg:col-span-2">
            등록된 지오펜스가 없습니다.
          </div>
        )}
      </div>
    </section>
  );
}
