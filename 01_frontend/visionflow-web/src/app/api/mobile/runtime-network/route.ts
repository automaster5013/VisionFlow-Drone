import { NextResponse } from "next/server";

import { loadMobileHttpsRuntimeProfile } from "@/lib/server/mobile-https-runtime";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const security = await getOperatorSecurityStatus();

  if (!security) {
    return NextResponse.json(
      {
        success: false,
        code: "BACKEND_UNAVAILABLE",
        message: "운영자 인증 상태를 확인할 수 없습니다.",
      },
      {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  if (security.enabled && !security.authenticated) {
    return NextResponse.json(
      {
        success: false,
        code: "OPERATOR_AUTHENTICATION_REQUIRED",
        message: "로그인 후 모바일 HTTPS 자동 감지 정보를 확인하세요.",
      },
      {
        status: 401,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  return NextResponse.json(
    await loadMobileHttpsRuntimeProfile(),
    {
      status: 200,
      headers: {
        "Cache-Control": "no-store",
        Vary: "Cookie",
      },
    },
  );
}
