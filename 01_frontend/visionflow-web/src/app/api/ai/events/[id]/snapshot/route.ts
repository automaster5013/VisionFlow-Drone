import { type NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

const BACKEND_API_URL = (
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

const MAX_SNAPSHOT_BYTES = 10 * 1024 * 1024;

interface RouteContext {
  params: Promise<{
    id: string;
  }>;
}

export async function GET(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params;

  if (!/^\d+$/.test(id)) {
    return NextResponse.json(
      { message: "잘못된 AI 이벤트 ID입니다." },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/ai/events/${encodeURIComponent(id)}/snapshot`,
      await withBackendOperatorAuth({
        method: "GET",
        headers: {
          Accept: "image/jpeg",
        },
        cache: "no-store",
      }),
    );

    const body = await response.arrayBuffer();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Content-Type":
          response.headers.get("content-type") ?? "application/octet-stream",
        ...(response.headers.get("content-disposition")
          ? {
              "Content-Disposition": response.headers.get(
                "content-disposition",
              )!,
            }
          : {}),
      },
    });
  } catch (error) {
    console.error("AI 이벤트 스냅샷 프록시 오류:", error);

    return NextResponse.json(
      {
        message: "백엔드 AI 이벤트 스냅샷 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  context: RouteContext,
) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const { id } = await context.params;
  if (!/^\d+$/.test(id)) {
    return NextResponse.json(
      { message: "잘못된 AI 이벤트 ID입니다." },
      { status: 400 },
    );
  }

  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return NextResponse.json(
      { message: "스냅샷 업로드 요청 형식이 올바르지 않습니다." },
      { status: 400 },
    );
  }

  const file = incoming.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json(
      { message: "저장할 JPEG 파일을 선택해야 합니다." },
      { status: 400 },
    );
  }

  const normalizedName = file.name.toLocaleLowerCase("en-US");
  const normalizedType = file.type.toLocaleLowerCase("en-US");
  const hasJpegExtension =
    normalizedName.endsWith(".jpg") ||
    normalizedName.endsWith(".jpeg");

  if (
    file.size === 0 ||
    file.size > MAX_SNAPSHOT_BYTES ||
    !hasJpegExtension ||
    (normalizedType !== "" && normalizedType !== "image/jpeg")
  ) {
    return NextResponse.json(
      {
        message:
          "10MB 이하의 JPEG(.jpg/.jpeg) 파일만 저장할 수 있습니다.",
      },
      { status: 400 },
    );
  }

  const formData = new FormData();
  formData.set("file", file, file.name);

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/ai/events/${encodeURIComponent(id)}/snapshot`,
      await withBackendOperatorAuth({
        method: "PUT",
        headers: { Accept: "application/json" },
        body: formData,
        cache: "no-store",
      }),
    );
    const body = await response.text();

    return new NextResponse(body || null, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error(
      "AI 이벤트 수동 스냅샷 저장 프록시 오류:",
      error,
    );

    return NextResponse.json(
      {
        message:
          "백엔드 AI 이벤트 스냅샷 저장 API에 연결할 수 없습니다.",
      },
      { status: 502 },
    );
  }
}

export async function DELETE(
  request: NextRequest,
  context: RouteContext,
) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) {
    return rejected;
  }

  const { id } = await context.params;

  if (!/^\d+$/.test(id)) {
    return NextResponse.json(
      { message: "잘못된 AI 이벤트 ID입니다." },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(
      `${BACKEND_API_URL}/api/ai/events/${encodeURIComponent(id)}/snapshot`,
      await withBackendOperatorAuth({
        method: "DELETE",
        headers: { Accept: "application/json" },
        cache: "no-store",
      }),
    );

    if (response.status === 204) {
      return new NextResponse(null, {
        status: 204,
        headers: { "Cache-Control": "no-store" },
      });
    }

    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("AI 이벤트 스냅샷 삭제 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 AI 이벤트 스냅샷 삭제 API에 연결할 수 없습니다." },
      { status: 502 },
    );
  }
}
