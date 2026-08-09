import { type NextRequest, NextResponse } from "next/server";

import {
  isOperatorPairingId,
  proxyOperatorPairingRequest,
} from "@/lib/server/operator-pairing";
import { isSameOriginRequest } from "@/lib/server/same-origin";

interface RouteContext {
  params: Promise<{ pairingId: string }>;
}

function invalidPairingId() {
  return NextResponse.json(
    {
      success: false,
      code: "INVALID_OPERATOR_PAIRING_ID",
      message: "QR 페어링 ID 형식이 올바르지 않습니다.",
    },
    { status: 400 },
  );
}

export async function GET(
  request: NextRequest,
  context: RouteContext,
) {
  const { pairingId } = await context.params;
  if (!isOperatorPairingId(pairingId)) {
    return invalidPairingId();
  }

  return proxyOperatorPairingRequest(
    request,
    `/api/security/pairings/${encodeURIComponent(pairingId)}`,
    "GET",
    { authenticated: true },
  );
}

export async function DELETE(
  request: NextRequest,
  context: RouteContext,
) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json(
      {
        success: false,
        code: "CROSS_ORIGIN_OPERATOR_PAIRING_DENIED",
        message: "다른 출처에서 QR 페어링을 취소할 수 없습니다.",
      },
      { status: 403 },
    );
  }

  const { pairingId } = await context.params;
  if (!isOperatorPairingId(pairingId)) {
    return invalidPairingId();
  }

  return proxyOperatorPairingRequest(
    request,
    `/api/security/pairings/${encodeURIComponent(pairingId)}`,
    "DELETE",
    { authenticated: true },
  );
}
