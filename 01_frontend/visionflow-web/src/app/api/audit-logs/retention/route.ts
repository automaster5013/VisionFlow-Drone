import { proxyAuditRequest } from "@/lib/server/audit-log-proxy";

export async function GET() {
    return proxyAuditRequest("/api/audit-logs/retention");
}
