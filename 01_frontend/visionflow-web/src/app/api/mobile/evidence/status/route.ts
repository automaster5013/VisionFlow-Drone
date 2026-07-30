import { NextResponse } from "next/server";

import { loadMobileEvidenceStatus } from "@/lib/mobile-evidence";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
    const status = await loadMobileEvidenceStatus();

    return NextResponse.json(status, {
        status: 200,
        headers: {
            "Cache-Control": "no-store",
        },
    });
}
