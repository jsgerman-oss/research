// Theme toggle click handler. Extracted from ThemeToggle.astro so it
// bundles to an external `/assets/*.js` chunk that matches the page's
// CSP `script-src 'self'` directive. Inline `<script>` blocks would
// require a sha256 hash in CSP, but only the bootstrap script's hash
// is computed at build time, so any other inline script is blocked.
//
// Pre-paint logic still lives inline in Layout.astro (its hash IS in
// the CSP). This file only handles user-initiated clicks.
//
// flagshipsyst-6b9 (SOLID SRP-001 + STRIDE T-05) + CSP-bundling fix.

const VALID_THEMES = ["light", "dark"] as const;
type Theme = (typeof VALID_THEMES)[number];
const STORAGE_KEY = "flagship-theme";

function isValidTheme(v: unknown): v is Theme {
  return typeof v === "string" && (VALID_THEMES as readonly string[]).includes(v);
}

function readTheme(): Theme {
  const html = document.documentElement.getAttribute("data-theme");
  return isValidTheme(html) ? html : "dark";
}

function writeTheme(t: Theme) {
  document.documentElement.setAttribute("data-theme", t);
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "light" ? "#fafaf7" : "#07090f");
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    /* localStorage unavailable (private mode, full disk, disabled) — silent. */
  }
}

export function initThemeToggle() {
  const btn = document.querySelector<HTMLButtonElement>("[data-theme-toggle]");
  if (!btn) return;

  const initial = readTheme();
  btn.setAttribute("aria-pressed", String(initial === "light"));

  btn.addEventListener("click", () => {
    const next: Theme = readTheme() === "light" ? "dark" : "light";
    writeTheme(next);
    btn.setAttribute("aria-pressed", String(next === "light"));
  });

  // Sanitize-on-load: if some other tab wrote a bogus value, normalize.
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null && !isValidTheme(stored)) {
      localStorage.setItem(STORAGE_KEY, initial);
    }
  } catch {
    /* localStorage unavailable — silent. */
  }
}
