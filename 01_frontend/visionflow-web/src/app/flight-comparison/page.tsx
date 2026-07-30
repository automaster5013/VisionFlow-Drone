import type { Metadata } from "next";

import { FlightSessionComparison } from "@/components/dashboard/flight-session-comparison";

export const metadata: Metadata = {
  title: "비행 성과 비교 | VisionFlow",
};

export const dynamic = "force-dynamic";

interface FlightComparisonPageProps {
  searchParams: Promise<
    Record<string, string | string[] | undefined>
  >;
}

function firstQueryValue(
  value: string | string[] | undefined,
): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function safeComparisonKey(
  value: string | string[] | undefined,
): string | undefined {
  const candidate = firstQueryValue(value)?.trim();

  return candidate &&
    candidate.length <= 80 &&
    /^\d+\|[^|]{1,64}$/.test(candidate)
    ? candidate
    : undefined;
}

export default async function FlightComparisonPage({
  searchParams,
}: FlightComparisonPageProps) {
  const query = await searchParams;

  return (
    <FlightSessionComparison
      initialLeftKey={safeComparisonKey(query.left)}
      initialRightKey={safeComparisonKey(query.right)}
    />
  );
}
