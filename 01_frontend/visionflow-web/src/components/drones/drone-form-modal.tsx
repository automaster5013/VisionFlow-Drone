"use client";

import {
    useState,
    type FormEvent,
} from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import type {
    ApiErrorResponse,
    ApiResponse,
    Drone,
    DroneCreateRequest,
    DroneStatus,
    DroneUpdateRequest,
} from "@/types/drone";

type FormMode = "create" | "edit";

interface DroneFormModalProps {
    mode: FormMode;
    drone?: Drone | null;
    onClose: () => void;
    onSuccess: () => void;
}

interface DroneFormState {
    droneCode: string;
    name: string;
    modelName: string;
    serialNumber: string;
    status: DroneStatus;
    rtspUrl: string;
    latitude: string;
    longitude: string;
    altitude: string;
    batteryLevel: string;
}

const initialFormState: DroneFormState = {
    droneCode: "",
    name: "",
    modelName: "",
    serialNumber: "",
    status: "OFFLINE",
    rtspUrl: "",
    latitude: "",
    longitude: "",
    altitude: "",
    batteryLevel: "",
};

function createInitialFormState(
    mode: FormMode,
    drone?: Drone | null,
): DroneFormState {
    if (mode === "edit" && drone) {
        return {
            droneCode: drone.droneCode,
            name: drone.name,
            modelName: drone.modelName ?? "",
            serialNumber: drone.serialNumber ?? "",
            status: drone.status,
            rtspUrl: drone.rtspUrl ?? "",
            latitude:
                drone.latitude !== null
                    ? String(drone.latitude)
                    : "",
            longitude:
                drone.longitude !== null
                    ? String(drone.longitude)
                    : "",
            altitude:
                drone.altitude !== null
                    ? String(drone.altitude)
                    : "",
            batteryLevel:
                drone.batteryLevel !== null
                    ? String(drone.batteryLevel)
                    : "",
        };
    }

    return {
        ...initialFormState,
    };
}

function nullableNumber(value: string): number | null {
    const trimmed = value.trim();

    if (!trimmed) {
        return null;
    }

    const parsed = Number(trimmed);

    return Number.isFinite(parsed) ? parsed : null;
}

export function DroneFormModal({
                                   mode,
                                   drone,
                                   onClose,
                                   onSuccess,
                               }: DroneFormModalProps) {
    const [form, setForm] = useState<DroneFormState>(() =>
        createInitialFormState(mode, drone),
    );

    const [submitting, setSubmitting] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const { canOperate, operateDeniedReason } = useOperatorAccess();

    const [fieldErrors, setFieldErrors] = useState<
        Record<string, string>
    >({});

    function updateField(
        field: keyof DroneFormState,
        value: string,
    ): void {
        setForm((current) => ({
            ...current,
            [field]: value,
        }));

        setFieldErrors((current) => {
            if (!current[field]) {
                return current;
            }

            const next = { ...current };
            delete next[field];

            return next;
        });
    }

    async function handleSubmit(
        event: FormEvent<HTMLFormElement>,
    ): Promise<void> {
        event.preventDefault();

        if (!canOperate) {
            setMessage(operateDeniedReason);
            return;
        }

        setSubmitting(true);
        setMessage(null);
        setFieldErrors({});

        try {
            const response =
                mode === "create"
                    ? await createDrone()
                    : await updateDrone();

            const body = (await response.json()) as
                | ApiResponse<Drone>
                | ApiErrorResponse;

            if (!response.ok || !body.success) {
                const errorBody = body as ApiErrorResponse;

                setMessage(
                    errorBody.message || "요청 처리에 실패했습니다.",
                );

                setFieldErrors(errorBody.errors ?? {});
                return;
            }

            onSuccess();
            onClose();
        } catch (error) {
            setMessage(
                error instanceof Error
                    ? error.message
                    : "요청 중 알 수 없는 오류가 발생했습니다.",
            );
        } finally {
            setSubmitting(false);
        }
    }

    function createDrone(): Promise<Response> {
        const payload: DroneCreateRequest = {
            droneCode: form.droneCode.trim(),
            name: form.name.trim(),
            modelName: form.modelName.trim() || null,
            serialNumber: form.serialNumber.trim() || null,
            status: form.status,
            rtspUrl: form.rtspUrl.trim() || null,
            latitude: nullableNumber(form.latitude),
            longitude: nullableNumber(form.longitude),
            altitude: nullableNumber(form.altitude),
            batteryLevel: nullableNumber(form.batteryLevel),
            lastConnectedAt: null,
        };

        return fetch("/api/drones", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
    }

    function updateDrone(): Promise<Response> {
        if (!drone) {
            throw new Error("수정할 드론 정보가 없습니다.");
        }

        const payload: DroneUpdateRequest = {
            name: form.name.trim(),
            modelName: form.modelName.trim() || null,
            serialNumber: form.serialNumber.trim() || null,
            rtspUrl: form.rtspUrl.trim() || null,
        };

        return fetch(`/api/drones/${drone.id}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
    }

    const title =
        mode === "create" ? "드론 등록" : "드론 정보 수정";

    return (
        <div
            className={[
                "fixed inset-0 z-50 flex items-center justify-center",
                "bg-slate-950/50 p-4",
            ].join(" ")}
            role="dialog"
            aria-modal="true"
            aria-labelledby="drone-form-title"
        >
            <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-xl">
                <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
                    <div>
                        <h2
                            id="drone-form-title"
                            className="text-xl font-bold text-slate-950"
                        >
                            {title}
                        </h2>

                        <p className="mt-1 text-sm text-slate-500">
                            드론 식별 정보와 영상 스트림 정보를 입력합니다.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        disabled={submitting}
                        className="rounded-lg px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100"
                    >
                        닫기
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6">
                    {!canOperate && operateDeniedReason && (
                        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                            {operateDeniedReason}
                        </div>
                    )}
                    {message && (
                        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                            {message}
                        </div>
                    )}

                    <div className="grid gap-5 md:grid-cols-2">
                        <FormField
                            label="드론 코드"
                            required
                            error={fieldErrors.droneCode}
                        >
                            <input
                                value={form.droneCode}
                                onChange={(event) =>
                                    updateField("droneCode", event.target.value)
                                }
                                disabled={mode === "edit"}
                                placeholder="DRONE-001"
                                className={inputClassName}
                            />
                        </FormField>

                        <FormField
                            label="드론 이름"
                            required
                            error={fieldErrors.name}
                        >
                            <input
                                value={form.name}
                                onChange={(event) =>
                                    updateField("name", event.target.value)
                                }
                                placeholder="Vision Eagle 1"
                                className={inputClassName}
                            />
                        </FormField>

                        <FormField
                            label="모델명"
                            error={fieldErrors.modelName}
                        >
                            <input
                                value={form.modelName}
                                onChange={(event) =>
                                    updateField("modelName", event.target.value)
                                }
                                placeholder="DJI Mini 4 Pro"
                                className={inputClassName}
                            />
                        </FormField>

                        <FormField
                            label="시리얼 번호"
                            error={fieldErrors.serialNumber}
                        >
                            <input
                                value={form.serialNumber}
                                onChange={(event) =>
                                    updateField("serialNumber", event.target.value)
                                }
                                placeholder="VF-DJI-0001"
                                className={inputClassName}
                            />
                        </FormField>

                        {mode === "create" && (
                            <FormField label="초기 상태">
                                <select
                                    value={form.status}
                                    onChange={(event) =>
                                        updateField("status", event.target.value)
                                    }
                                    className={inputClassName}
                                >
                                    <option value="OFFLINE">오프라인</option>
                                    <option value="ONLINE">온라인</option>
                                    <option value="FLYING">비행 중</option>
                                    <option value="CHARGING">충전 중</option>
                                    <option value="MAINTENANCE">점검 중</option>
                                    <option value="ERROR">오류</option>
                                </select>
                            </FormField>
                        )}

                        <FormField
                            label="배터리 잔량"
                            error={fieldErrors.batteryLevel}
                        >
                            <input
                                type="number"
                                min="0"
                                max="100"
                                value={form.batteryLevel}
                                onChange={(event) =>
                                    updateField(
                                        "batteryLevel",
                                        event.target.value,
                                    )
                                }
                                disabled={mode === "edit"}
                                placeholder="100"
                                className={inputClassName}
                            />
                        </FormField>

                        <div className="md:col-span-2">
                            <FormField
                                label="RTSP URL"
                                error={fieldErrors.rtspUrl}
                            >
                                <input
                                    value={form.rtspUrl}
                                    onChange={(event) =>
                                        updateField("rtspUrl", event.target.value)
                                    }
                                    placeholder="rtsp://192.168.0.100:8554/live"
                                    className={inputClassName}
                                />
                            </FormField>
                        </div>

                        {mode === "create" && (
                            <>
                                <FormField
                                    label="위도"
                                    error={fieldErrors.latitude}
                                >
                                    <input
                                        type="number"
                                        step="any"
                                        min="-90"
                                        max="90"
                                        value={form.latitude}
                                        onChange={(event) =>
                                            updateField(
                                                "latitude",
                                                event.target.value,
                                            )
                                        }
                                        placeholder="37.5665"
                                        className={inputClassName}
                                    />
                                </FormField>

                                <FormField
                                    label="경도"
                                    error={fieldErrors.longitude}
                                >
                                    <input
                                        type="number"
                                        step="any"
                                        min="-180"
                                        max="180"
                                        value={form.longitude}
                                        onChange={(event) =>
                                            updateField(
                                                "longitude",
                                                event.target.value,
                                            )
                                        }
                                        placeholder="126.9780"
                                        className={inputClassName}
                                    />
                                </FormField>

                                <FormField label="고도">
                                    <input
                                        type="number"
                                        step="any"
                                        value={form.altitude}
                                        onChange={(event) =>
                                            updateField(
                                                "altitude",
                                                event.target.value,
                                            )
                                        }
                                        placeholder="0"
                                        className={inputClassName}
                                    />
                                </FormField>
                            </>
                        )}
                    </div>

                    <div className="mt-8 flex justify-end gap-3 border-t border-slate-200 pt-5">
                        <button
                            type="button"
                            onClick={onClose}
                            disabled={submitting || !canOperate}
                            title={canOperate ? undefined : operateDeniedReason ?? undefined}
                            className="rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        >
                            취소
                        </button>

                        <button
                            type="submit"
                            disabled={submitting}
                            className="rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {submitting
                                ? "처리 중..."
                                : mode === "create"
                                    ? "등록하기"
                                    : "저장하기"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

const inputClassName = [
    "mt-2 w-full rounded-lg border border-slate-300",
    "bg-white px-3 py-2.5 text-sm text-slate-900",
    "outline-none transition",
    "focus:border-sky-500 focus:ring-2 focus:ring-sky-100",
    "disabled:cursor-not-allowed disabled:bg-slate-100",
].join(" ");

interface FormFieldProps {
    label: string;
    required?: boolean;
    error?: string;
    children: React.ReactNode;
}

function FormField({
                       label,
                       required = false,
                       error,
                       children,
                   }: FormFieldProps) {
    return (
        <label className="block text-sm font-medium text-slate-700">
      <span>
        {label}
          {required && (
              <span className="ml-1 text-red-500">*</span>
          )}
      </span>

            {children}

            {error && (
                <span className="mt-1 block text-xs text-red-600">
          {error}
        </span>
            )}
        </label>
    );
}
