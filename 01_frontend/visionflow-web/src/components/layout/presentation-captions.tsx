"use client";

import { useSyncExternalStore } from "react";

const KEY = "visionflow-presentation-captions-v1";
const EVENT = "visionflow-captions-change";
const captions = [
  ["대시보드", "VisionFlow는 AI 안전 탐지와 비행 데이터를 통합하는 드론 관제 시스템입니다."],
  ["통합 시연", "실제 드론 대신 더미 영상과 가상 텔레메트리로 관제 흐름을 시연합니다."],
  ["통합 시연", "영상은 실제 AI로 분석하고, 위치·고도·배터리는 같은 비행 세션에 전송합니다."],
  ["드론 관제", "지도에서 위치와 고도, 배터리 변화를 확인합니다. 가상 데이터는 ‘시연 중’으로 구분합니다."],
  ["AI 추론", "사람·안전모·안전모 미착용·안전조끼를 탐지하고 영상에 표시합니다."],
  ["AI 추론", "안전모 미착용이 탐지되면 화면 중앙에 붉은 경고가 천천히 깜빡입니다."],
  ["통합 시연", "영상과 가상 비행 데이터를 함께 일시정지하고 재개할 수 있습니다."],
  ["비행 기록", "종료한 세션에는 비행 경로와 AI 탐지 이벤트가 저장되어 다시 확인할 수 있습니다."],
  ["마무리", "영상 분석부터 위치 관제, 비행 기록 확인까지 하나의 흐름으로 연결합니다."],
];
function snapshot() {
  try { return localStorage.getItem(KEY) ?? "off"; } catch { return "off"; }
}
function subscribe(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(EVENT, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(EVENT, notify);
  };
}
function save(value: string) {
  try { localStorage.setItem(KEY, value); } catch { return; }
  window.dispatchEvent(new Event(EVENT));
}

export function PresentationCaptions({ showcase = false }: { showcase?: boolean }) {
  const value = useSyncExternalStore(subscribe, snapshot, () => "off");
  const index = /^\d+$/.test(value) ? Number(value) : -1;
  const active = index >= 0 && index < captions.length;
  if (!active) return <button className={`vf-caption-launch${showcase ? " vf-caption-launch-showcase" : ""}`} onClick={() => save("0")}>발표 자막 켜기</button>;
  return (
    <section className="vf-caption-panel" aria-label="발표용 자막">
      <p className="vf-caption-text" aria-live="polite" aria-atomic="true">{captions[index][1]}</p>
      <div className="vf-caption-controls">
        <span>{index + 1} / {captions.length} · {captions[index][0]}</span>
        <button onClick={() => save(String(index - 1))} disabled={index === 0}>이전</button>
        <button onClick={() => save(String(index + 1))} disabled={index === captions.length - 1}>다음</button>
        <button onClick={() => save("0")}>처음</button>
        <button onClick={() => save("off")}>자막 끄기</button>
      </div>
    </section>
  );
}
