"use client";

import { useRef, useState, type FormEvent } from "react";

const MAX_SNAPSHOT_BYTES = 10 * 1024 * 1024;

interface ManualSnapshotControlProps {
  eventId: number;
  hasSnapshot: boolean;
  onStored: () => void;
}

type UploadState = "idle" | "uploading" | "success" | "error";

async function responseMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = (await response.json()) as unknown;
    if (
      typeof body === "object" &&
      body !== null &&
      "message" in body &&
      typeof body.message === "string"
    ) {
      return body.message;
    }
  } catch {
    // JSON 응답이 아니면 HTTP 상태 기반 메시지를 사용합니다.
  }
  return fallback;
}

export function ManualSnapshotControl({
  eventId,
  hasSnapshot,
  onStored,
}: ManualSnapshotControlProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [state, setState] = useState<UploadState>("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedFile || !confirmed) {
      setState("error");
      setMessage("JPEG 선택과 수동 저장 확인이 모두 필요합니다.");
      return;
    }

    const normalizedName = selectedFile.name.toLocaleLowerCase("en-US");
    const normalizedType = selectedFile.type.toLocaleLowerCase("en-US");
    const hasJpegExtension =
      normalizedName.endsWith(".jpg") || normalizedName.endsWith(".jpeg");

    if (
      selectedFile.size === 0 ||
      selectedFile.size > MAX_SNAPSHOT_BYTES ||
      !hasJpegExtension ||
      (normalizedType !== "" && normalizedType !== "image/jpeg")
    ) {
      setState("error");
      setMessage("10MB 이하의 JPEG(.jpg/.jpeg) 파일만 선택할 수 있습니다.");
      return;
    }

    setState("uploading");
    setMessage("");

    const formData = new FormData();
    formData.set("file", selectedFile, selectedFile.name);

    try {
      const response = await fetch(`/api/ai/events/${eventId}/snapshot`, {
        method: "PUT",
        body: formData,
        credentials: "same-origin",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(
          await responseMessage(
            response,
            `스냅샷 저장 요청이 실패했습니다. (HTTP ${response.status})`,
          ),
        );
      }

      setSelectedFile(null);
      setConfirmed(false);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      setState("success");
      setMessage("선택한 JPEG를 수동 개인정보 스냅샷으로 저장했습니다.");
      onStored();
    } catch (error) {
      setState("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "수동 스냅샷 저장 중 오류가 발생했습니다.",
      );
    }
  }

  return (
    <section
      data-manual-snapshot-control
      className="vf-event-snapshot rounded-2xl border border-cyan-700/60 bg-cyan-950/20 p-5"
    >
      <h3 className="text-sm font-black text-cyan-100">
        개인정보 스냅샷 수동 저장
      </h3>
      <p className="mt-2 text-xs leading-5 text-cyan-100/75">
        자동 저장은 OFF 상태입니다. OPERATOR/ADMIN이 로컬 JPEG를 직접
        선택하고 확인한 경우에만 저장하며, 브라우저 카메라 프레임을 자동
        캡처하지 않습니다.
      </p>

      {hasSnapshot && (
        <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-400/10 px-3 py-2 text-xs font-bold text-amber-100">
          이 이벤트에는 이미 저장 프레임이 있습니다. 새 JPEG를 저장하면 기존
          파일을 교체합니다.
        </p>
      )}

      <form onSubmit={submit} className="vf-event-snapshot__form mt-4 space-y-3">
        <label className="block">
          <span className="text-xs font-black text-slate-300">
            JPEG 파일 선택
          </span>
          <input
            ref={inputRef}
            type="file"
            accept=".jpg,.jpeg,image/jpeg"
            disabled={state === "uploading"}
            onChange={(changeEvent) => {
              setSelectedFile(changeEvent.target.files?.[0] ?? null);
              setConfirmed(false);
              setState("idle");
              setMessage("");
            }}
            className="vf-event-snapshot__input mt-2 block w-full rounded-xl border border-slate-600 bg-slate-950 px-3 py-2 text-xs text-slate-200 file:mr-3 file:rounded-lg file:border-0 file:bg-cyan-400 file:px-3 file:py-2 file:text-xs file:font-black file:text-slate-950"
          />
        </label>

        <label className="vf-event-snapshot__confirm flex items-start gap-2 rounded-xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-xs leading-5 text-slate-300">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={state === "uploading" || selectedFile === null}
            onChange={(changeEvent) => setConfirmed(changeEvent.target.checked)}
            className="mt-0.5 h-4 w-4 accent-cyan-400"
          />
          <span>
            이 파일을 이벤트 증적으로 저장할 필요를 확인했으며, 수동 저장
            작업이 감사로그에 기록되는 것을 확인했습니다.
          </span>
        </label>

        <button
          type="submit"
          disabled={
            state === "uploading" || selectedFile === null || !confirmed
          }
          className="vf-event-snapshot__submit w-full rounded-xl bg-cyan-400 px-4 py-3 text-sm font-black text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {state === "uploading"
            ? "수동 저장 중..."
            : hasSnapshot
              ? "선택한 JPEG로 교체"
              : "선택한 JPEG 수동 저장"}
        </button>
      </form>

      {message && (
        <p
          aria-live="polite"
          className={`mt-3 text-xs font-bold ${
            state === "error" ? "text-rose-300" : "text-emerald-300"
          }`}
        >
          {message}
        </p>
      )}
    </section>
  );
}
