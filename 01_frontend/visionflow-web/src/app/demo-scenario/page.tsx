import type { Metadata } from "next";

import { DemoScenarioConsole } from "@/components/demo/demo-scenario-console";

export const metadata: Metadata = {
    title: "발표 시연 콘솔 | VisionFlow",
};

export default function DemoScenarioPage() {
    return <DemoScenarioConsole />;
}
