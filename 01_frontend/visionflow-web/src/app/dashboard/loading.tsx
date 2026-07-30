export default function DashboardLoading() {
    return (
        <section aria-label="대시보드 로딩 중">
            <div className="mb-6">
                <div className="h-4 w-36 animate-pulse rounded bg-slate-200" />
                <div className="mt-3 h-9 w-52 animate-pulse rounded bg-slate-200" />
                <div className="mt-3 h-4 w-80 max-w-full animate-pulse rounded bg-slate-200" />
            </div>

            <div className="grid gap-5 md:grid-cols-2">
                {[1, 2].map((item) => (
                    <div
                        key={item}
                        className="h-44 animate-pulse rounded-2xl border border-slate-200 bg-white"
                    />
                ))}
            </div>

            <div className="mt-5 h-40 animate-pulse rounded-2xl border border-slate-200 bg-white" />
        </section>
    );
}