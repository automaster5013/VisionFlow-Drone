import { type NextRequest, NextResponse } from "next/server";

import {
  isOperatorPairingId,
  proxyOperatorPairingRequest,
} from "@/lib/server/operator-pairing";
import { isSameOriginRequest } from "@/lib/server/same-origin";

interface RouteContext {
  params: Promise<{ pairingId: string }>;
}

export async function POST(
  request: NextRequest,
  context: RouteContext,
) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_OPERATOR_PAIRING_CLAIM_DENIED",
        message: "다른 출처에서 QR 페어링을 요청할 수 없습니다.",
      },
      { status: 403 },
    );
  }

  const { pairingId } = await context.params;
  if (!isOperatorPairingId(pairingId)) {
    return NextResponse.json(
      {
        success: false,
        code: "INVALID_OPERATOR_PAIRING_ID",
        message: "QR 페어링 ID 형식이 올바르지 않습니다.",
      },
      { status: 400 },
    );
  }

  return proxyOperatorPairingRequest(
    request,
    `/api/security/pairings/${encodeURIComponent(pairingId)}/claim`,
    "POST",
    { authenticated: false },
  );
}
