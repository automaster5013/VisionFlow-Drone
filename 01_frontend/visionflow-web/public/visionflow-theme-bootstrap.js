(() => {
  const storageKey = "visionflow.theme-preference.v1";
  const allowed = new Set(["system", "light", "dark"]);
  let preference = "system";
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        const candidate = typeof parsed === "string" ? parsed : parsed?.preference;
        if (allowed.has(candidate)) preference = candidate;
      } catch {
        if (allowed.has(raw)) preference = raw;
      }
    }
  } catch {}
  const resolved = preference === "system"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
    : preference;
  const root = document.documentElement;
  root.dataset.theme = preference;
  root.dataset.resolvedTheme = resolved;
  root.style.colorScheme = resolved;
})();
