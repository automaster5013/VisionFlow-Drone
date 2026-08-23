"use client";

import { useEffect, useState } from "react";

const dateFormatter = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const timeFormatter = new Intl.DateTimeFormat("ko-KR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function CommandClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();

    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="vf-command-clock" aria-label="현재 로컬 시각">
      <span className="vf-command-clock__date">
        {now ? dateFormatter.format(now) : "----.--.--"}
      </span>
      <time
        className="vf-command-clock__time"
        dateTime={now?.toISOString()}
      >
        {now ? timeFormatter.format(now) : "--:--:--"}
      </time>
    </div>
  );
}
