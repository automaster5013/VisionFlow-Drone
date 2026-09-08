"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { presentationTelemetry } from "@/lib/presentation-telemetry";

type Session = { sessionId: string; droneId: number };
type State = "READY" | "RUNNING" | "PAUSED" | "STOPPED";
const DEVICE = "presentation-simulator-001";

async function api(path: string, method: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch(path, { method, signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000), cache: "no-store", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw new Error(`${response.status}: ${(await response.text()).slice(0, 220)}`);
  return response.status === 204 ? null : response.json();
}

export function PresentationReplayConsole() {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const current = useRef<Session | null>(null);
  const active = useRef(false);
  const request = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const [state, setState] = useState<State>("READY");
  const [session, setSession] = useState<Session | null>(null);
  const [busy, setBusy] = useState(false);
  const [droneId, setDroneId] = useState(3);
  const [latitude, setLatitude] = useState(37.5665);
  const [longitude, setLongitude] = useState(126.978);
  const [repeat, setRepeat] = useState(false);
  const [duration, setDuration] = useState(0);
  const [position, setPosition] = useState(0);
  const [frames, setFrames] = useState(0);
  const [telemetryCount, setTelemetryCount] = useState(0);
  const [loopCount, setLoopCount] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [sample, setSample] = useState<ReturnType<typeof presentationTelemetry> | null>(null);

  function halt() {
    active.current = false;
    generation.current += 1;
    request.current?.abort();
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    video.current?.pause();
  }

  useEffect(() => {
    const release = () => {
      active.current = false;
      generation.current += 1;
      request.current?.abort();
      if (timer.current) clearTimeout(timer.current);
      const owned = current.current;
      if (owned) {
        navigator.sendBeacon(`/api/drones/${owned.droneId}/flight-sessions/${encodeURIComponent(owned.sessionId)}/abort`);
        current.current = null;
      }
    };
    window.addEventListener("pagehide", release);
    return () => { window.removeEventListener("pagehide", release); release(); };
  }, []);

  async function pausePresentation() {
    const owned = current.current;
    if (!owned || busy) return;
    halt(); setState("PAUSED"); setBusy(true);
    try {
      await api(`/api/drones/${owned.droneId}/flight-sessions/${encodeURIComponent(owned.sessionId)}/pause`, "POST");
      setError(null);
    } catch (e) {
      setError(`일시정지 기록 실패: 이 구간은 통신 공백으로 남을 수 있습니다. ${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); }
  }

  async function finish(landed = false) {
    halt();
    setState("PAUSED");
    const owned = current.current;
    if (!owned) return;
    setBusy(true);
    try {
      if (landed && video.current) {
        const point = presentationTelemetry(video.current.duration, video.current.duration, { latitude, longitude });
        await api(`/api/drones/${owned.droneId}/telemetry`, "PATCH", { ...point, sourceDeviceId: DEVICE, flightSessionId: owned.sessionId });
        setSample(point); setPosition(video.current.duration); setTelemetryCount(value => value + 1);
      }
      await api(`/api/drones/${owned.droneId}/flight-sessions/${encodeURIComponent(owned.sessionId)}/complete`, "POST");
      current.current = null;
      setSession(null);
      setState("STOPPED");
      setError(null);
    } catch (e) {
      setError(`세션 종료 실패. 종료 버튼으로 재시도하세요. ${e instanceof Error ? e.message : e}`);
    } finally { setBusy(false); }
  }

  function run(owned: Session) {
    const epoch = ++generation.current;
    active.current = true;
    const controller = new AbortController();
    request.current = controller;
    let lastTelemetry = -Infinity;
    let lastPosition = 0;
    const tick = async () => {
      if (!active.current || generation.current !== epoch) return;
      const v = video.current;
      const c = canvas.current;
      if (!v || !c) return;
      try {
        if (v.readyState >= 2 && !v.paused) {
          const seconds = v.currentTime;
          if (seconds < lastPosition) { setLoopCount(value => value + 1); lastTelemetry = -Infinity; }
          lastPosition = seconds;
          setPosition(seconds);
          if (performance.now() - lastTelemetry >= 1000) {
            const point = presentationTelemetry(seconds, v.duration, { latitude, longitude });
            await api(`/api/drones/${owned.droneId}/telemetry`, "PATCH", { ...point, sourceDeviceId: DEVICE, flightSessionId: owned.sessionId }, controller.signal);
            if (generation.current !== epoch) return;
            lastTelemetry = performance.now();
            setSample(point);
            setTelemetryCount(value => value + 1);
          }
          c.width = Math.round(Math.min(v.videoWidth, 960));
          c.height = Math.max(1, Math.round(v.videoHeight * c.width / v.videoWidth));
          const context = c.getContext("2d");
          if (!context) throw new Error("영상 캔버스를 사용할 수 없습니다.");
          context.drawImage(v, 0, 0, c.width, c.height);
          const jpeg = await new Promise<Blob>((resolve, reject) => c.toBlob(blob => blob ? resolve(blob) : reject(new Error("영상 인코딩 실패")), "image/jpeg", .8));
          if (generation.current !== epoch) return;
          const query = new URLSearchParams({ droneId: String(owned.droneId), sessionId: owned.sessionId, sourceId: DEVICE, sourceType: "DUMMY_VIDEO", capturedAt: new Date().toISOString() });
          const response = await fetch(`/api/ai/ingest/frame?${query}`, { method: "POST", body: jpeg, headers: { "Content-Type": "image/jpeg" }, signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]) });
          if (!response.ok) throw new Error(`AI 영상 전송 실패: ${response.status}`);
          const result = await response.json();
          if (result.accepted === false) throw new Error("AI 서버가 프레임을 수락하지 않았습니다.");
          if (generation.current !== epoch) return;
          setFrames(value => value + 1);
        }
      } catch (e) {
        if (generation.current !== epoch) return;
        halt();
        setState("PAUSED");
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
      if (active.current && generation.current === epoch) timer.current = setTimeout(tick, 200);
    };
    void tick();
  }

  async function start() {
    if (busy || active.current) return;
    setBusy(true); setError(null);
    try {
      const v = video.current;
      if (!v || !Number.isFinite(v.duration) || v.duration <= 0) throw new Error("더미영상 로딩을 기다리세요.");
      if (!Number.isInteger(droneId) || droneId < 1) throw new Error("유효한 드론 ID를 입력하세요.");
      presentationTelemetry(0, v.duration, { latitude, longitude });
      let owned = current.current;
      if (!owned) {
        const response = await api(`/api/drones/${droneId}/flight-sessions`, "POST", { name: "[시연] 더미영상·가상 텔레메트리", description: "SIMULATOR: 35m 순환 경로, 30m 고도, 영상 시각 동기화. 실제 비행 아님.", sourceDeviceId: DEVICE });
        if (!response?.sessionId || response.status !== "ACTIVE") throw new Error("서버 비행 세션 생성에 실패했습니다.");
        owned = { sessionId: response.sessionId, droneId };
        current.current = owned; setSession(owned);
        v.currentTime = 0; setPosition(0); setFrames(0); setTelemetryCount(0); setLoopCount(1);
      }
      await api(`/api/drones/${owned.droneId}/flight-sessions/${encodeURIComponent(owned.sessionId)}/resume`, "POST");
      v.loop = repeat;
      await v.play();
      setState("RUNNING");
      run(owned);
    } catch (e) {
      halt(); setState(current.current ? "PAUSED" : "READY");
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  const panel = "rounded-2xl border p-5";
  const panelStyle = { background: "var(--vf-surface-1)", borderColor: "var(--vf-border)", color: "var(--vf-text-primary)" };
  const button = "rounded-xl bg-blue-700 px-5 py-3 font-bold text-white disabled:opacity-40";
  return <main className="mx-auto max-w-6xl space-y-5 p-5" style={{ color: "var(--vf-text-primary)" }}>
    <header className={panel} style={panelStyle}>
      <p className="font-bold" style={{ color: "var(--vf-accent-strong)" }}>SIMULATOR · 발표 전용</p>
      <h1 className="my-2 text-3xl font-black">영상·텔레메트리 통합 시연</h1>
      <p>실제 AI 영상과 가상 비행 데이터를 같은 서버 세션으로 전송합니다. 경로는 기준점에서 반경 35m, 고도는 최대 30m입니다.</p>
      <p className="mt-2 text-sm">이 탭을 열어 두세요. 탭을 닫으면 전송을 중단합니다. 반복할 때 영상·경로·가상 배터리가 함께 처음으로 돌아갑니다.</p>
      <div className="mt-3 flex gap-4 underline"><Link href="/demo-mode">기존 시연 화면</Link><Link href="/mobile-flight">스마트폰 실감지</Link><a href={`/drones?droneId=${droneId}`} target="_blank" rel="noreferrer">관제 새 창</a><a href="/ai-preview" target="_blank" rel="noreferrer">AI 추론 새 창</a></div>
    </header>
    <section className={panel} style={panelStyle}>
      <div className="grid gap-4 sm:grid-cols-3">
        {[["드론 ID", droneId, setDroneId], ["기준 위도", latitude, setLatitude], ["기준 경도", longitude, setLongitude]].map(([label, value, setter]) => <label key={String(label)} className="font-bold">{String(label)}<input className="mt-2 block w-full rounded-lg border p-3" style={panelStyle} type="number" step="any" value={Number(value)} disabled={!!session || busy} onChange={e => (setter as (value: number) => void)(Number(e.target.value))} /></label>)}
      </div>
      <label className="mt-4 flex gap-2"><input type="checkbox" checked={repeat} disabled={!!session || busy} onChange={e => setRepeat(e.target.checked)} />영상·경로 반복 재생</label>
      <div className="mt-4 flex flex-wrap gap-3">
        <button className={button} disabled={busy || state === "RUNNING" || !duration} onClick={() => void start()}>{session ? "재개" : "통합 시연 시작"}</button>
        <button className={button} disabled={busy || state !== "RUNNING"} onClick={() => void pausePresentation()}>일시정지</button>
        <button className={button} disabled={busy || !session} onClick={() => void finish()}>종료 · 세션 저장</button>
        <button className={button} disabled={busy || !!session} onClick={() => { if (video.current) video.current.currentTime = 0; setPosition(0); setSample(null); setFrames(0); setTelemetryCount(0); setLoopCount(1); setState("READY"); setError(null); }}>초기화</button>
      </div>
      <p className="mt-3">{state === "RUNNING" ? "재생 중" : state === "PAUSED" ? "일시정지" : state === "STOPPED" ? "종료됨" : "시작 대기"} · {position.toFixed(1)} / {duration.toFixed(1)}초 · {loopCount}회차</p>
      <p className="mt-2 break-all text-sm">세션: {session?.sessionId ?? "시작 시 서버 발급"} · 영상 수락 {frames}회 · 가상 텔레메트리 저장 {telemetryCount}회</p>
      {error && <p role="alert" className="mt-3 rounded-lg bg-red-950 p-3 text-red-100">{error}</p>}
    </section>
    <video ref={video} className="aspect-video w-full rounded-2xl bg-black" src="/demo/presentation-dummy.mp4" muted playsInline preload="metadata" onLoadedMetadata={() => setDuration(Number.isFinite(video.current?.duration) ? video.current!.duration : 0)} onEnded={() => void finish(true)} onError={() => setError("발표용 영상을 불러오지 못했습니다.")} />
    <canvas ref={canvas} hidden />
    <section className={panel} style={panelStyle}><h2 className="font-black">SIMULATOR · 마지막 저장값</h2><p className="mt-2">위치 {sample ? `${sample.latitude.toFixed(6)}, ${sample.longitude.toFixed(6)}` : "—"} · 고도 {sample?.altitude.toFixed(1) ?? "—"}m · 속도 {sample?.groundSpeed.toFixed(1) ?? "—"}m/s · 배터리 {sample?.batteryLevel ?? "—"}%</p></section>
  </main>;
}
