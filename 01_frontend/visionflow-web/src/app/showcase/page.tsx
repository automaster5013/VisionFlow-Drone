import Link from "next/link";

const capabilities = [
  ["실시간 관제", "드론 위치·배터리·고도와 비행 세션을 한 화면에서 확인합니다."],
  ["Vision AI", "FastAPI·YOLO·OpenCV 기반 영상 분석과 안전 이벤트 흐름을 연결합니다."],
  ["데이터 추적", "텔레메트리·탐지 이벤트·비행 이력을 MySQL에 저장하고 다시 조회합니다."],
  ["운영 안정성", "Docker·AWS 하이브리드 배포, Health Check와 자동 Rollback을 검증했습니다."],
];

export default function ShowcasePage() {
  return (
    <main data-showcase className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto max-w-7xl px-6 pb-20 pt-8 sm:px-10 lg:px-16 lg:pt-12">
        <nav className="flex items-center justify-between border-b border-white/10 pb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-400 font-black text-slate-950">VF</div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.3em] text-cyan-300">PyvaOps</p>
              <p className="font-semibold">VisionFlow-Drone</p>
            </div>
          </div>
          <Link href="/operator-login" className="rounded-full border border-white/20 px-4 py-2 text-sm font-semibold transition hover:border-cyan-300 hover:text-cyan-200">
            운영 콘솔 로그인
          </Link>
        </nav>

        <div className="grid gap-12 pb-20 pt-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pt-24">
          <div>
            <p className="mb-5 text-sm font-bold uppercase tracking-[0.35em] text-cyan-300">Drone · Vision AI · Safety Operations</p>
            <h1 className="showcase-hero-title max-w-3xl text-4xl font-black leading-[1.14] tracking-[-0.035em] sm:text-5xl lg:text-[clamp(3.25rem,4.4vw,4.5rem)]">
              <span className="block whitespace-normal lg:whitespace-nowrap">영상과 텔레메트리를 연결하는</span>
              <span className="mt-2 block text-cyan-300">지능형 드론 관제 플랫폼</span>
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300">
              VisionFlow-Drone은 가상 드론과 실제 드론 확장 경로를 하나의 표준 파이프라인으로 연결합니다. 영상 입력, AI 탐지, 비행 데이터, 이벤트 이력을 운영 화면에서 추적할 수 있도록 설계했습니다.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <a href="https://visionflow-drone.cloud/demo/presentation-dummy.mp4" className="showcase-primary-button rounded-full bg-cyan-300 px-6 py-3 font-bold text-slate-950 transition hover:bg-cyan-200">발표 영상 재생</a>
              <Link href="/presentation-replay" className="rounded-full border border-white/20 px-6 py-3 font-bold transition hover:border-cyan-300 hover:text-cyan-200">인터랙티브 데모</Link>
              <Link href="/operator-login" className="rounded-full border border-white/20 px-6 py-3 font-bold transition hover:border-cyan-300 hover:text-cyan-200">관제 화면 들어가기</Link>
            </div>
          </div>

          <div className="rounded-3xl border border-cyan-300/20 bg-gradient-to-br from-cyan-300/15 via-slate-900 to-indigo-400/10 p-6 shadow-2xl shadow-cyan-950/40">
            <div className="rounded-2xl border border-white/10 bg-slate-950/80 p-5">
              <div className="mb-8 flex items-center justify-between text-xs text-slate-400"><span>VISIONFLOW COMMAND CENTER</span><span className="text-emerald-300">● SYSTEM READY</span></div>
              <div className="grid grid-cols-2 gap-3">
                {[["03", "Connected drones"], ["94", "Accepted frames"], ["25", "Telemetry points"], ["04", "AI events"]].map(([value, label]) => <div key={label} className="rounded-xl border border-white/10 bg-white/[0.04] p-4"><p className="text-3xl font-black text-cyan-200">{value}</p><p className="mt-1 text-xs text-slate-400">{label}</p></div>)}
              </div>
              <div className="mt-4 rounded-xl border border-emerald-300/20 bg-emerald-300/10 p-4 text-sm text-emerald-100">Local Edge AI → AWS Backend / MySQL → Web Dashboard</div>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {capabilities.map(([title, description]) => <article key={title} className="rounded-2xl border border-white/10 bg-white/[0.04] p-5"><h2 className="text-lg font-bold text-cyan-200">{title}</h2><p className="mt-3 text-sm leading-6 text-slate-300">{description}</p></article>)}
        </div>
      </section>

      <section className="border-y border-white/10 bg-white/[0.03]">
        <div className="mx-auto grid max-w-7xl gap-10 px-6 py-16 sm:px-10 lg:grid-cols-2 lg:px-16">
          <div><p className="text-sm font-bold uppercase tracking-[0.3em] text-cyan-300">How it works</p><h2 className="mt-3 text-3xl font-black">입력부터 운영 증적까지</h2><p className="mt-5 leading-7 text-slate-300">브라우저·스마트폰·시험 영상 또는 향후 DJI 입력을 어댑터로 수용하고, AI 분석 결과와 텔레메트리를 백엔드·데이터베이스·관제 UI로 전달합니다.</p></div>
          <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-xl border border-white/10 p-4"><p className="font-bold">01 · Input</p><p className="mt-2 text-sm text-slate-400">Video, telemetry, flight session</p></div><div className="rounded-xl border border-white/10 p-4"><p className="font-bold">02 · Analyze</p><p className="mt-2 text-sm text-slate-400">FastAPI, YOLO, OpenCV</p></div><div className="rounded-xl border border-white/10 p-4"><p className="font-bold">03 · Persist</p><p className="mt-2 text-sm text-slate-400">Spring Boot, MySQL, WebSocket</p></div><div className="rounded-xl border border-white/10 p-4"><p className="font-bold">04 · Operate</p><p className="mt-2 text-sm text-slate-400">Next.js dashboard, AWS hybrid</p></div></div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-16 text-center sm:px-10 lg:px-16"><p className="text-sm text-slate-400">최종 발표 시연은 가상 드론·더미 영상 기반이며, DJI 실기체와 AWS AI 확장은 후속 검증 범위입니다.</p><div className="mt-6 flex justify-center gap-3"><a href="https://github.com/automaster5013/VisionFlow-Drone" className="rounded-full border border-white/20 px-5 py-2 text-sm font-semibold hover:border-cyan-300">GitHub 저장소</a><Link href="/operator-login" className="showcase-primary-button rounded-full bg-cyan-300 px-5 py-2 text-sm font-bold text-slate-950">운영 콘솔 로그인</Link></div></section>
    </main>
  );
}
