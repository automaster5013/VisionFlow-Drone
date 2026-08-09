import type { Metadata } from "next";

import { OperatorPairClient } from "@/components/security/operator-pair-client";

export const metadata: Metadata = {
  title: "QR 기기 연결",
};

export const dynamic = "force-dynamic";

export default function OperatorPairPage() {
  return <OperatorPairClient />;
}
