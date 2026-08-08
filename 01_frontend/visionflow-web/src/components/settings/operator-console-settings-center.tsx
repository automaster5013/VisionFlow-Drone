"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import {
  DEFAULT_OPERATOR_CONSOLE_PREFERENCES,
  readOperatorConsolePreferences,
  resetOperatorConsolePreferences,
  writeOperatorConsolePreferences,
} from "@/lib/operator-console-settings";
import {
  EVENT_TIME_RANGE_OPTIONS,
  STATISTICS_RANGE_OPTIONS,
  type EventTimeRange,
  type OperatorConsolePreferences,
} from "@/types/operator-console-settings";

const EVENT_RANGE_LABELS: Record<EventTimeRange, string> = {
  "1H": "최근 1시간",
  "6H": "최근 6시간",
  "24H": "최근 24시간",
  "7D": "최근 7일",
  ALL: "전체 기간",
};

function formatDateTime(value: string | null): string {
  if (!value) return "아직 이 세션에서 저장하지 않음";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "저장 시각 확인 필요";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function Panel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-black text-slate-950">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-5 rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <span>
        <span className="block font-black text-slate-950">{label}</span>
        <span className="mt-1 block text-sm leading-6 text-slate-500">
          {description}
        </span>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-5 w-5 shrink-0 accent-cyan-600"
      />
    </label>
  );
}

export function OperatorConsoleSettingsCenter() {
  const { status } = useOperatorAccess();
  const [preferences, setPreferences] = useState<OperatorConsolePreferences>(
    () => readOperatorConsolePreferences(),
  );
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [message, setMessage] = useState(
    "저장한 값은 다음 화면 진입부터 해당 관제 화면의 기본값으로 적용됩니다.",
  );

  function updatePreference<K extends keyof OperatorConsolePreferences>(
    key: K,
    value: OperatorConsolePreferences[K],
  ) {
    setPreferences((current) => ({ ...current, [key]: value }));
  }

  function save() {
    try {
      const updatedAt = writeOperatorConsolePreferences(preferences);
      setSavedAt(updatedAt);
      setMessage("현재 브라우저의 관제 기본값을 저장했습니다.");
    } catch {
      setMessage("브라우저 저장소를 사용할 수 없어 기본값을 저장하지 못했습니다.");
    }
  }

  function reset() {
    try {
      const defaults = resetOperatorConsolePreferences();
      setPreferences(defaults);
      setSavedAt(null);
      setMessage("브라우저 저장값을 제거하고 제품 기본값으로 되돌렸습니다.");
    } catch {
      setPreferences({ ...DEFAULT_OPERATOR_CONSOLE_PREFERENCES });
      setMessage("화면 값은 기본값으로 되돌렸지만 브라우저 저장소를 정리하지 못했습니다.");
    }
  }

  const identity = status?.enabled === false
    ? "로컬 보안 비활성 모드"
    : status?.authenticated
      ? `${status.username ?? "운영자"} · ${status.role ?? "역할 확인 필요"}`
      : "로그인 필요";

  return (
    <div data-operator-console-settings-center className="mx-auto max-w-[1450px] space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.24em] text-cyan-700">
            Operator console preferences
          </p>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">
            운영 설정 센터
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            이벤트·통계·AI 모델 관제 화면의 시작 기본값을 현재 브라우저에만 안전하게 저장합니다.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-xl border border-slate-300 bg-white px-5 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50"
          >
            기본값 복원
          </button>
          <button
            type="button"
            onClick={save}
            className="rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white hover:bg-slate-800"
          >
            설정 저장
          </button>
        </div>
      </header>

      <section className="rounded-[2rem] bg-gradient-to-br from-slate-950 via-slate-950 to-indigo-950 p-6 text-white shadow-xl sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.22em] text-cyan-300">
              Current browser profile
            </p>
            <h2 className="mt-2 text-2xl font-black">브라우저별 관제 기본값</h2>
          </div>
          <span className="rounded-full border border-emerald-400/30 bg-emerald-500/15 px-4 py-2 text-sm font-bold text-emerald-100">
            서버 변경 없음
          </span>
        </div>
        <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-cyan-400/25 bg-cyan-500/10 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-cyan-100/70">Event refresh</p>
            <p className="mt-3 text-2xl font-black">{preferences.eventAutoRefresh ? "15초 사용" : "수동"}</p>
          </div>
          <div className="rounded-2xl border border-violet-400/25 bg-violet-500/10 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-violet-100/70">Event range</p>
            <p className="mt-3 text-2xl font-black">{EVENT_RANGE_LABELS[preferences.eventTimeRange]}</p>
          </div>
          <div className="rounded-2xl border border-sky-400/25 bg-sky-500/10 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-sky-100/70">Statistics</p>
            <p className="mt-3 text-2xl font-black">최근 {preferences.statisticsRangeDays}일</p>
          </div>
          <div className="rounded-2xl border border-emerald-400/25 bg-emerald-500/10 p-5">
            <p className="text-xs font-bold uppercase tracking-[0.15em] text-emerald-100/70">AI model refresh</p>
            <p className="mt-3 text-2xl font-black">{preferences.aiModelAutoRefresh ? "30초 사용" : "수동"}</p>
          </div>
        </div>
        <p className="mt-5 text-sm text-slate-300" aria-live="polite">
          {message} · 저장 시각 {formatDateTime(savedAt)}
        </p>
      </section>

      <div className="grid gap-7 xl:grid-cols-2">
        <Panel
          title="자동 갱신 기본값"
          description="각 화면에 처음 진입할 때 자동 갱신을 켤지 정합니다. 화면 안에서 언제든 임시로 변경할 수 있습니다."
        >
          <div className="space-y-4">
            <Toggle
              label="통합 이벤트 관제 · 15초"
              description="AI 추론·경보, 지오펜스와 Incident를 주기적으로 다시 조회합니다."
              checked={preferences.eventAutoRefresh}
              onChange={(checked) => updatePreference("eventAutoRefresh", checked)}
            />
            <Toggle
              label="운영 통계 센터 · 30초"
              description="비행·신뢰도·정비·AI 통계의 마지막 정상 데이터를 주기적으로 갱신합니다."
              checked={preferences.statisticsAutoRefresh}
              onChange={(checked) => updatePreference("statisticsAutoRefresh", checked)}
            />
            <Toggle
              label="AI 모델 운영 센터 · 30초"
              description="모델·GPU·추론·입력 큐·스트림·경보 상태를 주기적으로 갱신합니다."
              checked={preferences.aiModelAutoRefresh}
              onChange={(checked) => updatePreference("aiModelAutoRefresh", checked)}
            />
          </div>
        </Panel>

        <Panel
          title="조회 범위 기본값"
          description="통합 이벤트와 운영 통계 화면에 처음 적용할 기간을 선택합니다."
        >
          <fieldset>
            <legend className="text-sm font-black text-slate-800">이벤트 시간 범위</legend>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {EVENT_TIME_RANGE_OPTIONS.map((range) => (
                <label key={range} className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 p-4 font-bold text-slate-700">
                  <input
                    type="radio"
                    name="event-time-range"
                    value={range}
                    checked={preferences.eventTimeRange === range}
                    onChange={() => updatePreference("eventTimeRange", range)}
                    className="h-4 w-4 accent-cyan-600"
                  />
                  {EVENT_RANGE_LABELS[range]}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="mt-6">
            <legend className="text-sm font-black text-slate-800">통계 표본 기간</legend>
            <div className="mt-3 grid grid-cols-3 gap-3">
              {STATISTICS_RANGE_OPTIONS.map((days) => (
                <label key={days} className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-200 p-4 font-bold text-slate-700">
                  <input
                    type="radio"
                    name="statistics-range"
                    value={days}
                    checked={preferences.statisticsRangeDays === days}
                    onChange={() => updatePreference("statisticsRangeDays", days)}
                    className="h-4 w-4 accent-cyan-600"
                  />
                  {days}일
                </label>
              ))}
            </div>
          </fieldset>
        </Panel>
      </div>

      <div className="grid gap-7 xl:grid-cols-2">
        <Panel
          title="보안 및 데이터 경계"
          description="이 화면이 저장하거나 변경하지 않는 시스템 경계를 명확히 표시합니다."
        >
          <dl className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <dt className="text-xs font-bold text-slate-500">현재 운영자</dt>
              <dd className="mt-2 font-black text-slate-950">{identity}</dd>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <dt className="text-xs font-bold text-slate-500">저장 범위</dt>
              <dd className="mt-2 font-black text-slate-950">현재 브라우저 프로필</dd>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <dt className="text-xs font-bold text-slate-500">서버·DB·AI 설정</dt>
              <dd className="mt-2 font-black text-emerald-700">변경하지 않음</dd>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <dt className="text-xs font-bold text-slate-500">비밀·키·모델 경로</dt>
              <dd className="mt-2 font-black text-emerald-700">저장하지 않음</dd>
            </div>
          </dl>
        </Panel>

        <Panel
          title="연결된 운영 화면"
          description="설정 저장 후 각 화면으로 이동해 적용된 시작 기본값을 확인합니다."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              ["이벤트 관제", "/events"],
              ["운영 통계", "/statistics"],
              ["AI 모델", "/models"],
              ["보안 상태", "/security-status"],
            ].map(([label, href]) => (
              <Link key={href} href={href} className="rounded-xl border border-slate-200 px-4 py-4 text-center text-sm font-black text-slate-800 hover:border-cyan-300 hover:text-cyan-800">
                {label}
              </Link>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
