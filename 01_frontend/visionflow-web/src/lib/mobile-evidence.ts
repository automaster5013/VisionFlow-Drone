import { createHash, timingSafeEqual } from "node:crypto";
import { lstat, readdir, readFile } from "node:fs/promises";
import path from "node:path";

import type {
    AvailableMobileEvidenceStatus,
    MobileEvidenceDetails,
    MobileEvidenceReportStatus,
    MobileEvidenceStatus,
    MobileEvidenceSummary,
} from "@/types/mobile-evidence-status";

const REPORT_NAME_PATTERN =
    /^visionflow-smartphone-e2e-\d{8}T\d{6}(?:\d+)?Z\.json$/;
const MAX_REPORT_BYTES = 1024 * 1024;
const FRESHNESS_LIMIT_HOURS = 30 * 24;
const FUTURE_CLOCK_TOLERANCE_HOURS = 1;

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isNonNegativeInteger(value: unknown): value is number {
    return (
        typeof value === "number" &&
        Number.isInteger(value) &&
        value >= 0
    );
}

function isPositiveInteger(value: unknown): value is number {
    return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isNullableIsoDate(value: unknown): value is string | null {
    return (
        value === null ||
        (typeof value === "string" && Number.isFinite(Date.parse(value)))
    );
}

function isReportStatus(value: unknown): value is MobileEvidenceReportStatus {
    return (
        value === "SMARTPHONE_E2E_PASS" ||
        value === "SMARTPHONE_E2E_BLOCKED"
    );
}

function isSummary(value: unknown): value is MobileEvidenceSummary {
    return (
        isRecord(value) &&
        isNonNegativeInteger(value.passed) &&
        isNonNegativeInteger(value.blocked)
    );
}

function maskSessionId(value: string): string {
    if (value.length <= 12) {
        return "기록됨";
    }

    return `${value.slice(0, 8)}…${value.slice(-4)}`;
}

function parseEvidence(value: unknown): MobileEvidenceDetails | null {
    if (
        !isRecord(value) ||
        !isPositiveInteger(value.droneId) ||
        typeof value.sessionId !== "string" ||
        value.sessionId.length < 12 ||
        typeof value.sessionStatus !== "string" ||
        typeof value.startedAt !== "string" ||
        !Number.isFinite(Date.parse(value.startedAt)) ||
        !isNullableIsoDate(value.endedAt) ||
        !isNonNegativeInteger(value.durationSeconds) ||
        typeof value.sourceDeviceIdRecorded !== "boolean" ||
        !isNonNegativeInteger(value.telemetryCount) ||
        !isNonNegativeInteger(value.mobileSensorCount) ||
        !isNonNegativeInteger(value.gpsValueCount) ||
        !isNonNegativeInteger(value.orientationValueCount) ||
        !isNonNegativeInteger(value.aiEventCount) ||
        !isNonNegativeInteger(value.detectionCount)
    ) {
        return null;
    }

    return {
        droneId: value.droneId,
        sessionIdMasked: maskSessionId(value.sessionId),
        sessionStatus: value.sessionStatus,
        startedAt: value.startedAt,
        endedAt: value.endedAt,
        durationSeconds: value.durationSeconds,
        sourceDeviceIdRecorded: value.sourceDeviceIdRecorded,
        telemetryCount: value.telemetryCount,
        mobileSensorCount: value.mobileSensorCount,
        gpsValueCount: value.gpsValueCount,
        orientationValueCount: value.orientationValueCount,
        aiEventCount: value.aiEventCount,
        detectionCount: value.detectionCount,
    };
}

function hasPrivacyGuarantees(value: unknown): boolean {
    return (
        isRecord(value) &&
        value.exactCoordinatesRecorded === false &&
        value.operatorKeyRecorded === false &&
        value.sessionTokenRecorded === false &&
        value.rawImageRecorded === false &&
        value.rawVideoRecorded === false
    );
}

function getCandidateDirectories(): string[] {
    const configuredDirectory =
        process.env.VISIONFLOW_MOBILE_EVIDENCE_DIRECTORY?.trim();
    const candidates = [
        configuredDirectory,
        path.resolve(process.cwd(), "artifacts", "mobile-readiness"),
        path.resolve(
            process.cwd(),
            "..",
            "..",
            "..",
            "artifacts",
            "mobile-readiness",
        ),
    ].filter((value): value is string => Boolean(value));

    return [...new Set(candidates)];
}

async function findEvidenceDirectory(): Promise<string | null> {
    for (const candidate of getCandidateDirectories()) {
        try {
            const metadata = await lstat(candidate);

            if (metadata.isDirectory() && !metadata.isSymbolicLink()) {
                return candidate;
            }
        } catch {
            // 다음 후보 경로를 확인합니다.
        }
    }

    return null;
}

async function findLatestReport(directory: string): Promise<string | null> {
    const entries = await readdir(directory, { withFileTypes: true });
    const reportNames = entries
        .filter(
            (entry) =>
                entry.isFile() &&
                !entry.isSymbolicLink() &&
                REPORT_NAME_PATTERN.test(entry.name),
        )
        .map((entry) => entry.name)
        .sort((left, right) => right.localeCompare(left, "en"));

    return reportNames[0] ?? null;
}

function unavailable(message: string): MobileEvidenceStatus {
    return {
        available: false,
        status: "SMARTPHONE_E2E_UNAVAILABLE",
        integrity: "NOT_AVAILABLE",
        freshness: "UNKNOWN",
        generatedAt: null,
        message,
    };
}

function invalid(message: string): MobileEvidenceStatus {
    return {
        available: false,
        status: "SMARTPHONE_E2E_INVALID",
        integrity: "FAILED",
        freshness: "UNKNOWN",
        generatedAt: null,
        message,
    };
}

async function readRegularFile(
    filePath: string,
    maxBytes: number,
): Promise<Buffer> {
    const metadata = await lstat(filePath);

    if (
        !metadata.isFile() ||
        metadata.isSymbolicLink() ||
        metadata.size > maxBytes
    ) {
        throw new Error("증적 파일 형식 또는 크기가 허용 범위를 벗어났습니다.");
    }

    return readFile(filePath);
}

function verifyChecksum(
    reportBytes: Buffer,
    checksumBytes: Buffer,
    reportName: string,
): string | null {
    const checksumText = checksumBytes
        .toString("utf8")
        .replace(/^\uFEFF/, "")
        .trim();
    const match = /^([a-fA-F0-9]{64})\s{2}([^\r\n]+)$/.exec(checksumText);

    if (!match || match[2] !== reportName) {
        return null;
    }

    const expected = Buffer.from(match[1].toLowerCase(), "hex");
    const actualHex = createHash("sha256").update(reportBytes).digest("hex");
    const actual = Buffer.from(actualHex, "hex");

    return timingSafeEqual(expected, actual) ? actualHex : null;
}

function parseVerifiedReport(
    reportBytes: Buffer,
    reportName: string,
    checksumSha256: string,
    now: Date,
): MobileEvidenceStatus {
    let payload: unknown;

    try {
        payload = JSON.parse(
            reportBytes.toString("utf8").replace(/^\uFEFF/, ""),
        );
    } catch {
        return invalid("스마트폰 증적 JSON 형식이 올바르지 않습니다.");
    }

    if (
        !isRecord(payload) ||
        payload.schemaVersion !== 1 ||
        payload.project !== "visionflow" ||
        payload.operation !== "SMARTPHONE_E2E_VERIFICATION" ||
        !isReportStatus(payload.status) ||
        typeof payload.generatedAt !== "string" ||
        !Number.isFinite(Date.parse(payload.generatedAt)) ||
        !isSummary(payload.summary) ||
        !hasPrivacyGuarantees(payload.privacy)
    ) {
        return invalid("스마트폰 증적 스키마 또는 개인정보 보호 표식이 올바르지 않습니다.");
    }

    const evidence = parseEvidence(payload.evidence);

    if (!evidence) {
        return invalid("스마트폰 증적의 측정값 형식이 올바르지 않습니다.");
    }

    const ageHours =
        (now.getTime() - Date.parse(payload.generatedAt)) / (60 * 60 * 1000);

    if (ageHours < -FUTURE_CLOCK_TOLERANCE_HOURS) {
        return invalid("스마트폰 증적 생성 시각이 현재 시각보다 지나치게 미래입니다.");
    }

    const result: AvailableMobileEvidenceStatus = {
        available: true,
        status: payload.status,
        integrity: "VERIFIED",
        freshness:
            ageHours <= FRESHNESS_LIMIT_HOURS && ageHours >= 0
                ? "FRESH"
                : "STALE",
        generatedAt: payload.generatedAt,
        ageHours: Math.max(0, Math.round(ageHours * 10) / 10),
        artifactName: reportName,
        checksumSha256,
        summary: payload.summary,
        evidence,
    };

    return result;
}

export async function loadMobileEvidenceStatus(
    now = new Date(),
): Promise<MobileEvidenceStatus> {
    const directory = await findEvidenceDirectory();

    if (!directory) {
        return unavailable(
            "스마트폰 실센서 증적 폴더를 찾지 못했습니다. 증적을 생성하거나 Compose 읽기 전용 볼륨을 확인하세요.",
        );
    }

    let reportName: string | null;

    try {
        reportName = await findLatestReport(directory);
    } catch (error) {
        console.error("스마트폰 증적 디렉터리 조회 오류:", error);
        return unavailable("스마트폰 실센서 증적 폴더를 읽을 수 없습니다.");
    }

    if (!reportName) {
        return unavailable(
            "생성된 스마트폰 실센서 E2E JSON 증적이 없습니다.",
        );
    }

    try {
        const reportPath = path.join(directory, reportName);
        const checksumPath = path.join(
            directory,
            reportName.replace(/\.json$/, ".sha256"),
        );
        const [reportBytes, checksumBytes] = await Promise.all([
            readRegularFile(reportPath, MAX_REPORT_BYTES),
            readRegularFile(checksumPath, 4096),
        ]);
        const checksumSha256 = verifyChecksum(
            reportBytes,
            checksumBytes,
            reportName,
        );

        if (!checksumSha256) {
            return invalid(
                "스마트폰 증적의 SHA-256 무결성 검증에 실패했습니다.",
            );
        }

        return parseVerifiedReport(
            reportBytes,
            reportName,
            checksumSha256,
            now,
        );
    } catch (error) {
        console.error("스마트폰 증적 파일 조회 오류:", error);
        return invalid(
            "스마트폰 증적 또는 SHA-256 파일을 안전하게 읽을 수 없습니다.",
        );
    }
}
