import { type NextRequest, NextResponse } from "next/server";

import { proxyOperatorPairingRequest } from "@/lib/server/operator-pairing";
import { isSameOriginRequest } from "@/lib/server/same-origin";

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_OPERATOR_PAIRING_DENIED",
        message: "다른 출처에서 QR 페어링을 생성할 수 없습니다.",
      },
      { status: 403 },
    );
  }

  return proxyOperatorPairingRequest(
    request,
    "/api/security/pairings",
    "POST",
    { authenticated: true },
  );
}
