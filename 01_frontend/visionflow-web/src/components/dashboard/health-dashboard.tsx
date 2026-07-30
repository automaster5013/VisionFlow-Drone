import { StatusCard } from "@/components/dashboard/status-card";
import { formatKoreanDateTime } from "@/lib/date";
import type { HealthData } from "@/types/health";

interface HealthDashboardProps {
    health: HealthData;
}

export function HealthDashboard({ health }: HealthDashboardProps) {
    return (
        <section aria-labelledby="system-health-title">
            <div className="mb-6">
                <p className="text-sm font-semibold uppercase tracking-wider text-sky-700">
                    System Monitoring
                </p>

                <h2
                    id="system-health-title"
                    className="mt-2 text-3xl font-bold tracking-tight text-slate-950"
                >
                    시스템 상태
                </h2>

                <p className="mt-2 text-sm leading-6 text-slate-600">
                    VisionFlow 관제 플랫폼의 주요 서비스 연결 상태를 확인합니다.
                </p>
            </div>

            <div className="grid gap-5 md:grid-cols-2">
                <StatusCard
                    title="Spring Boot API"
                    description="드론, 카메라, 이벤트 및 사용자 정보를 처리하는 업무 백엔드입니다."
                    status={health.applicationStatus}
                />

                <StatusCard
                    title="MySQL Database"
                    description="관제 장비, AI 탐지 이벤트와 시스템 설정을 저장하는 데이터베이스입니다."
                    status={health.databaseStatus}
                />
            </div>

            <article className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-lg font-bold text-slate-900">연결 정보</h3>

                <dl className="mt-5 grid gap-5 sm:grid-cols-2">
                    <div>
                        <dt className="text-sm font-medium text-slate-500">서비스명</dt>
                        <dd className="mt-1 font-mono text-sm text-slate-900">
                            {health.service}
                        </dd>
                    </div>

                    <div>
                        <dt className="text-sm font-medium text-slate-500">
                            최근 확인 시각
                        </dt>
                        <dd className="mt-1 text-sm text-slate-900">
                            {formatKoreanDateTime(health.checkedAt)}
                        </dd>
                    </div>
                </dl>
            </article>
        </section>
    );
}
