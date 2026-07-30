"use client";

import {
    useState,
    type FormEvent,
} from "react";
import { useRouter } from "next/navigation";

import type {
    ApiErrorResponse,
    ApiResponse,
    Drone,
    DroneTelemetryUpdateRequest,
} from "@/types/drone";

interface TelemetryUpdateFormProps {
    drone: Drone;
}

interface TelemetryFormState {
    latitude: string;
    longitude: string;
    altitude: string;
    batteryLevel: string;
}

function toNullableNumber(
    value: string,
): number | null {
    const trimmed = value.trim();

    if (!trimmed) {
        return null;
    }

    const number = Number(trimmed);

    return Number.isFinite(number)
        ? number
        : null;
}

export function TelemetryUpdateForm({
                                        drone,
                                    }: TelemetryUpdateFormProps) {
    const router = useRouter();

    const [form, setForm] =
        useState<TelemetryFormState>({
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
        });

    const [submitting, setSubmitting] =
        useState(false);

    const [message, setMessage] =
        useState<string | null>(null);

    const [successMessage, setSuccessMessage] =
        useState<string | null>(null);

    const [fieldErrors, setFieldErrors] = useState<
        Record<string, string>
    >({});

    function updateField(
        field: keyof TelemetryFormState,
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

        setSubmitting(true);
        setMessage(null);
        setSuccessMessage(null);
        setFieldErrors({});

        const payload: DroneTelemetryUpdateRequest = {
            latitude: toNullableNumber(form.latitude),
            longitude: toNullableNumber(form.longitude),
            altitude: toNullableNumber(form.altitude),
            batteryLevel: toNullableNumber(
                form.batteryLevel,
            ),
        };

        try {
            const response = await fetch(
                `/api/drones/${drone.id}/telemetry`,
                {
                    method: "PATCH",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify(payload),
                },
            );

            const body = (await response.json()) as
                | ApiResponse<Drone>
                | ApiErrorResponse;

            if (!response.ok || !body.success) {
                const errorBody =
                    body as ApiErrorResponse;

                setMessage(
                    errorBody.message ||
                    "텔레메트리 갱신에 실패했습니다.",
                );

                setFieldErrors(errorBody.errors ?? {});
                return;
            }

            setSuccessMessage(
                "텔레메트리 정보가 갱신되었습니다.",
            );

            router.refresh();
        } catch (error) {
            setMessage(
                error instanceof Error
                    ? error.message
                    : "텔레메트리 요청 중 오류가 발생했습니다.",
            );
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div>
                <h2 className="text-lg font-bold text-slate-950">
                    텔레메트리 갱신
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                    테스트 단계에서 위치, 고도와 배터리
                    정보를 수동으로 갱신합니다.
                </p>
            </div>

            <form
                onSubmit={handleSubmit}
                className="mt-6"
            >
                {message && (
                    <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                        {message}
                    </div>
                )}

                {successMessage && (
                    <div className="mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
                        {successMessage}
                    </div>
                )}

                <div className="grid gap-5 sm:grid-cols-2">
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
                            className={inputClassName}
                            placeholder="37.5665123"
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
                            className={inputClassName}
                            placeholder="126.9780456"
                        />
                    </FormField>

                    <FormField
                        label="고도"
                        error={fieldErrors.altitude}
                    >
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
                            className={inputClassName}
                            placeholder="42.5"
                        />
                    </FormField>

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
                            className={inputClassName}
                            placeholder="78"
                        />
                    </FormField>
                </div>

                <div className="mt-6 flex justify-end">
                    <button
                        type="submit"
                        disabled={submitting}
                        className="rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {submitting
                            ? "갱신 중..."
                            : "텔레메트리 갱신"}
                    </button>
                </div>
            </form>
        </article>
    );
}

const inputClassName = [
    "mt-2 w-full rounded-lg border border-slate-300",
    "bg-white px-3 py-2.5 text-sm text-slate-900",
    "outline-none transition",
    "focus:border-sky-500 focus:ring-2 focus:ring-sky-100",
].join(" ");

interface FormFieldProps {
    label: string;
    error?: string;
    children: React.ReactNode;
}

function FormField({
                       label,
                       error,
                       children,
                   }: FormFieldProps) {
    return (
        <label className="block text-sm font-medium text-slate-700">
            {label}

            {children}

            {error && (
                <span className="mt-1 block text-xs text-red-600">
          {error}
        </span>
            )}
        </label>
    );
}