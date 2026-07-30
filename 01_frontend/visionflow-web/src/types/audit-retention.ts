export interface AuditRetentionStatus {
    enabled: boolean;
    archiveConfirmed: boolean;
    dryRun: boolean;
    retentionDays: number;
    batchSize: number;
    cron: string;
    cutoff: string;
    eligibleCount: number;
    checkedAt: string;
}

export interface AuditRetentionExecution {
    enabled: boolean;
    trigger: string;
    retentionDays: number;
    batchSize: number;
    cutoff: string;
    deletedCount: number;
    remainingEligibleCount: number;
    executedAt: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isNonNegativeSafeInteger(value: unknown): value is number {
    return (
        typeof value === "number" &&
        Number.isSafeInteger(value) &&
        value >= 0
    );
}

function isPositiveSafeInteger(value: unknown): value is number {
    return isNonNegativeSafeInteger(value) && value > 0;
}

export function parseAuditRetentionStatus(
    value: unknown,
): AuditRetentionStatus | null {
    if (!isRecord(value)) return null;
    if (
        typeof value.enabled !== "boolean" ||
        typeof value.archiveConfirmed !== "boolean" ||
        typeof value.dryRun !== "boolean" ||
        !isPositiveSafeInteger(value.retentionDays) ||
        !isPositiveSafeInteger(value.batchSize) ||
        typeof value.cron !== "string" ||
        typeof value.cutoff !== "string" ||
        !isNonNegativeSafeInteger(value.eligibleCount) ||
        typeof value.checkedAt !== "string"
    ) {
        return null;
    }
    return {
        enabled: value.enabled,
        archiveConfirmed: value.archiveConfirmed,
        dryRun: value.dryRun,
        retentionDays: value.retentionDays,
        batchSize: value.batchSize,
        cron: value.cron,
        cutoff: value.cutoff,
        eligibleCount: value.eligibleCount,
        checkedAt: value.checkedAt,
    };
}
