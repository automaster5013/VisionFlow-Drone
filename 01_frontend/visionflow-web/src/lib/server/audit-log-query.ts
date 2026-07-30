import "server-only";

import { isAuditAction, isAuditEntityType } from "@/types/audit-log";

interface AuditLogSearchParseOptions {
    exportMode?: boolean;
}

export type AuditLogSearchParseResult =
    | { ok: true; params: URLSearchParams }
    | { ok: false; message: string };

export function parseAuditLogSearchParams(
    input: URLSearchParams,
    options: AuditLogSearchParseOptions = {},
): AuditLogSearchParseResult {
    const output = new URLSearchParams();

    if (options.exportMode) {
        const rawLimit = input.get("limit") ?? "5000";
        if (!/^\d+$/.test(rawLimit)) {
            return {
                ok: false,
                message: "CSV 내보내기 개수는 숫자여야 합니다.",
            };
        }
        const limit = Number(rawLimit);
        if (!Number.isInteger(limit) || limit < 1 || limit > 5000) {
            return {
                ok: false,
                message: "CSV 내보내기 개수는 1~5000이어야 합니다.",
            };
        }
        output.set("limit", String(limit));
    } else {
        const rawPage = input.get("page") ?? "0";
        const rawSize = input.get("size") ?? "30";
        if (!/^\d+$/.test(rawPage) || !/^\d+$/.test(rawSize)) {
            return {
                ok: false,
                message: "감사 로그 페이지와 조회 개수는 숫자여야 합니다.",
            };
        }
        const page = Number(rawPage);
        const size = Number(rawSize);
        if (!Number.isInteger(page) || page < 0) {
            return {
                ok: false,
                message: "감사 로그 페이지는 0 이상이어야 합니다.",
            };
        }
        if (!Number.isInteger(size) || size < 1 || size > 100) {
            return {
                ok: false,
                message: "감사 로그 조회 개수는 1~100이어야 합니다.",
            };
        }
        output.set("page", String(page));
        output.set("size", String(size));
    }

    const action = input.get("action")?.trim().toUpperCase() ?? "";
    if (action && !isAuditAction(action)) {
        return { ok: false, message: "지원하지 않는 감사 작업입니다." };
    }

    const entityType = input.get("entityType")?.trim().toUpperCase() ?? "";
    if (entityType && !isAuditEntityType(entityType)) {
        return {
            ok: false,
            message: "지원하지 않는 감사 대상 유형입니다.",
        };
    }

    const entityId = input.get("entityId")?.trim() ?? "";
    const actor = input.get("actor")?.trim() ?? "";
    if (entityId.length > 100 || actor.length > 100) {
        return {
            ok: false,
            message: "감사 대상 ID와 처리자는 100자 이하여야 합니다.",
        };
    }

    const from = input.get("from")?.trim() ?? "";
    const to = input.get("to")?.trim() ?? "";
    if (from && !Number.isFinite(Date.parse(from))) {
        return {
            ok: false,
            message: "감사 로그 시작 시각이 올바르지 않습니다.",
        };
    }
    if (to && !Number.isFinite(Date.parse(to))) {
        return {
            ok: false,
            message: "감사 로그 종료 시각이 올바르지 않습니다.",
        };
    }
    if (from && to && Date.parse(from) > Date.parse(to)) {
        return {
            ok: false,
            message: "감사 로그 시작 시각은 종료 시각보다 늦을 수 없습니다.",
        };
    }

    if (action) output.set("action", action);
    if (entityType) output.set("entityType", entityType);
    if (entityId) output.set("entityId", entityId);
    if (actor) output.set("actor", actor);
    if (from) output.set("from", from);
    if (to) output.set("to", to);
    return { ok: true, params: output };
}
