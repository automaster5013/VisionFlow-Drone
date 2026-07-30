import { StatusBadge } from "@/components/dashboard/status-badge";
import type { ServiceStatus } from "@/types/health";

interface StatusCardProps {
    title: string;
    description: string;
    status: ServiceStatus;
}

export function StatusCard({
                               title,
                               description,
                               status,
                           }: StatusCardProps) {
    return (
        <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-sm font-medium text-slate-500">시스템 구성요소</p>

                    <h2 className="mt-1 text-xl font-bold text-slate-900">{title}</h2>
                </div>

                <StatusBadge status={status} />
            </div>

            <p className="mt-5 text-sm leading-6 text-slate-600">{description}</p>
        </article>
    );
}