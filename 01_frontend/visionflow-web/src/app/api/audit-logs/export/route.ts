import { type NextRequest } from "next/server";

import {
    badAuditRequest,
    proxyAuditDownload,
} from "@/lib/server/audit-log-proxy";
import { parseAuditLogSearchParams } from "@/lib/server/audit-log-query";

export async function GET(request: NextRequest) {
    const parsed = parseAuditLogSearchParams(request.nextUrl.searchParams, {
        exportMode: true,
    });
    if (!parsed.ok) {
        return badAuditRequest(parsed.message);
    }
    return proxyAuditDownload(
        `/api/audit-logs/export?${parsed.params.toString()}`,
    );
}
