import { type NextRequest } from "next/server";

import {
    badAuditRequest,
    proxyAuditMutationRequest,
} from "@/lib/server/audit-log-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

export async function POST(request: NextRequest) {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    if (request.nextUrl.searchParams.get("confirm") !== "true") {
        return badAuditRequest(
            "감사 로그 정리를 실행하려면 confirm=true가 필요합니다.",
        );
    }
    if (request.nextUrl.searchParams.get("backupConfirmed") !== "true") {
        return badAuditRequest(
            "감사 로그 CSV 백업 후 backupConfirmed=true가 필요합니다.",
        );
    }
    return proxyAuditMutationRequest(
        "/api/audit-logs/retention/cleanup?confirm=true&backupConfirmed=true",
        request,
    );
}
