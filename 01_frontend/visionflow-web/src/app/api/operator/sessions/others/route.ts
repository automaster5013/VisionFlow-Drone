import { type NextRequest } from "next/server";

import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";
import { proxyOperatorSessionRequest } from "@/lib/server/operator-session-management";

export async function DELETE(request: NextRequest) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  return proxyOperatorSessionRequest(
    "/api/security/sessions/others?confirm=true",
    "DELETE",
  );
}
