import Link from "next/link";
import Image from "next/image";

const capabilities = [
  ["실시간 관제", "위치 · 배터리 · 고도"],
  ["Vision AI", "FastAPI · YOLO · OpenCV"],
  ["데이터 추적", "텔레메트리 · 이벤트 · 이력"],
  ["운영 안정성", "AWS · Health Check · Rollback"],
];

const workflow = ["01 영상·센서 입력", "02 AI 분석", "03 데이터 저장", "04 통합 관제"];

export default function ShowcasePage() {
  return (
    <main data-showcase className="showcase-page min-h-screen bg-slate-950 text-slate-100">
      <div className="showcase-shell mx-auto flex w-full max-w-7xl flex-col px-5 sm:px-8 lg:px-12">
        <nav className="showcase-nav flex shrink-0 items-center justify-between border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-400 font-black text-slate-950">VF</div>
            <div><p className="text-[10px] font-bold uppercase tracking-[0.3em] text-cyan-700">PyvaOps</p><p className="text-sm font-semibold">VisionFlow-Drone</p></div>
          </div>
          <Link href="/operator-login" className="showcase-secondary-button rounded-full border px-4 py-2 text-sm font-semibold transition">운영 콘솔 로그인</Link>
        </nav>

        <section className="showcase-hero grid flex-1 items-center gap-6 lg:grid-cols-[1.08fr_0.92fr] xl:gap-10" aria-labelledby="showcase-title">
          <div className="min-w-0">
            <p className="showcase-eyebrow mb-3 text-xs font-bold uppercase tracking-[0.28em]">Drone · Vision AI · Safety Operations</p>
            <h1 id="showcase-title" className="showcase-hero-title max-w-3xl text-[clamp(2rem,4.2vw,3.6rem)] font-black leading-[1.12] tracking-[-0.04em]">
              <span className="block">영상과 텔레메트리를</span>
              <span className="block">연결하는</span>
              <span className="showcase-hero-accent block">지능형 드론 관제 플랫폼</span>
            </h1>
            <p className="showcase-description mt-4 max-w-2xl text-base leading-7">
              가상 드론과 실제 드론의 확장 경로를 하나의 파이프라인으로 연결합니다. 영상·AI 탐지·비행 데이터와 이벤트 이력을 한눈에 추적합니다.
            </p>
            <div className="mt-6 flex flex-wrap gap-2.5">
              <a href="https://visionflow-drone.cloud/demo/presentation-dummy.mp4" className="showcase-primary-button rounded-full bg-cyan-300 px-5 py-3 text-sm font-bold transition">발표 영상 재생</a>
              <Link href="/presentation-replay" className="showcase-secondary-button rounded-full border px-5 py-3 text-sm font-bold transition">인터랙티브 데모</Link>
              <Link href="/operator-login" className="showcase-secondary-button rounded-full border px-5 py-3 text-sm font-bold transition">관제 화면 들어가기</Link>
            </div>
          </div>

          <div className="showcase-drone-card relative isolate overflow-hidden rounded-[1.75rem] border shadow-2xl">
            <Image src="/showcase/drone-hero.png" alt="산과 호수 위를 비행하는 쿼드콥터 드론" fill priority sizes="(max-width: 1024px) 100vw, 42vw" className="showcase-drone-image object-cover object-[68%_center]" />
            <div className="showcase-drone-wash absolute inset-0" />
            <div className="showcase-drone-top absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-4 sm:p-5">
              <div className="showcase-drone-brand rounded-xl px-3 py-2 backdrop-blur-md"><p className="text-[9px] font-bold uppercase tracking-[0.2em]">PyvaOps · Field Intelligence</p><p className="mt-0.5 text-sm font-semibold">VisionFlow-Drone</p></div>
              <span className="showcase-ready-pill whitespace-nowrap rounded-full px-2.5 py-1.5 text-[10px] font-bold shadow-sm">● SYSTEM READY</span>
            </div>
            <div className="showcase-drone-info absolute inset-x-3 bottom-3 z-10 rounded-2xl border p-4 shadow-xl backdrop-blur-xl sm:inset-x-4 sm:bottom-4 sm:p-5">
              <div className="mb-3 flex items-center justify-between gap-2"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-200">Mission snapshot</p><h2 className="mt-0.5 text-lg font-black text-white">하늘에서 관제까지</h2></div><span className="rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[10px] font-semibold text-white">LIVE SYSTEM</span></div>
              <div className="grid grid-cols-4 gap-2">
                {[["03", "드론"], ["94", "영상 프레임"], ["25", "텔레메트리"], ["04", "AI 이벤트"]].map(([value, label]) => <div key={label} className="showcase-drone-stat rounded-lg border px-2 py-2"><p className="text-xl font-black text-cyan-200">{value}</p><p className="mt-0.5 text-[10px] font-semibold text-slate-200">{label}</p></div>)}
              </div>
              <p className="showcase-drone-pipeline mt-2 rounded-lg border px-3 py-2 text-xs font-bold leading-5">Edge AI <span aria-hidden="true">→</span> AWS Backend <span aria-hidden="true">→</span> MySQL <span aria-hidden="true">→</span> Web Dashboard</p>
            </div>
          </div>
        </section>

        <section className="showcase-summary shrink-0" aria-label="주요 기능과 처리 흐름">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
            {capabilities.map(([title, description]) => <article key={title} className="showcase-capability rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 sm:px-4"><h2 className="showcase-capability-title text-sm font-extrabold">{title}</h2><p className="showcase-capability-copy mt-1 text-xs font-medium leading-5">{description}</p></article>)}
          </div>
          <div className="showcase-bottomline mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-white/10 pt-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1">{workflow.map((step) => <span key={step} className="showcase-workflow-item text-xs font-bold">{step}</span>)}</div>
            <div className="flex items-center gap-3"><span className="showcase-footnote text-[10px] font-medium">가상 드론·더미 영상 기반 시연 · DJI 실기체/AWS AI 확장은 후속 검증</span><a href="https://github.com/automaster5013/VisionFlow-Drone" className="showcase-secondary-button shrink-0 rounded-full border px-3 py-1.5 text-xs font-bold">GitHub</a></div>
          </div>
        </section>
      </div>
    </main>
  );
}
