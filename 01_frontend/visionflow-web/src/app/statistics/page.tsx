import type { Metadata } from "next";

import { OperationsStatisticsCenter } from "@/components/statistics/operations-statistics-center";

export const metadata: Metadata = {
  title: "운영 통계",
};

export const dynamic = "force-dynamic";

export default function StatisticsPage() {
  return <OperationsStatisticsCenter />;
}
