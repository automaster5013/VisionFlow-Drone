import { type NextRequest } from "next/server";

import {
    badAuditRequest,
    proxyAuditRequest,
} from "@/lib/server/audit-log-proxy";
import { parseAuditLogSearchParams } from "@/lib/server/audit-log-query";

export async function GET(request: NextRequest) {
    const parsed = parseAuditLogSearchParams(request.nextUrl.searchParams);
    if (!parsed.ok) {
        return badAuditRequest(parsed.message);
    }
    return proxyAuditRequest(`/api/audit-logs?${parsed.params.toString()}`);
}
