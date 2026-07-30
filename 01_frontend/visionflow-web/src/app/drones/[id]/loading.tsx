export default function DroneDetailLoading() {
    return (
        <section aria-label="드론 상세 로딩 중">
            <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
            <div className="mt-5 h-4 w-36 animate-pulse rounded bg-slate-200" />
            <div className="mt-3 h-9 w-64 animate-pulse rounded bg-slate-200" />
            <div className="mt-3 h-4 w-40 animate-pulse rounded bg-slate-200" />

            <div className="mt-7 grid gap-5 xl:grid-cols-3">
                <div className="space-y-5 xl:col-span-2">
                    <div className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white" />
                    <div className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white" />
                    <div className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white" />
                </div>

                <div className="h-96 animate-pulse rounded-2xl border border-slate-200 bg-white" />
            </div>
        </section>
    );
}