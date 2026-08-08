import type { Metadata } from "next";

import { OperatorConsoleSettingsCenter } from "@/components/settings/operator-console-settings-center";

export const metadata: Metadata = {
  title: "운영 설정",
};

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  return <OperatorConsoleSettingsCenter />;
}
