import { proxyOperatorSessionRequest } from "@/lib/server/operator-session-management";

export async function GET() {
  return proxyOperatorSessionRequest("/api/security/sessions", "GET");
}
