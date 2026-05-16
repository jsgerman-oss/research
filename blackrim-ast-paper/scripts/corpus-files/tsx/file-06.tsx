// Skill-card popover controller for SkillSystem.astro.
//
// Pattern:
//   - One <dialog> per page (the canonical site uses one SkillSystem
//     section per page, so a single dialog suffices).
//   - Each .skill-chip is a <button data-skill-slug> with the
//     description payload mirrored in [data-skill-desc] / -title /
//     -when. Click → fill the dialog body → showModal().
//   - Close: ESC (built-in to <dialog>), backdrop click (synthesized),
//     close button. Focus returns to the originating button on close.
//
// Why <dialog> + manual JS, not a framework component:
//   - Native modal semantics: focus trap, ESC, scroll lock, ::backdrop.
//   - Zero extra runtime; no React/Svelte for one popover.
//   - WCAG-compliant focus management once we set tabindex on close.
//
// blackrimsyst — UI fix Jay called out from production review.

interface SkillPayload {
  slug: string;
  title: string;
  when: string;
  description: string;
}

function readPayload(btn: HTMLElement): SkillPayload | null {
  const slug = btn.dataset.skillSlug;
  if (!slug) return null;
  return {
    slug,
    title: btn.dataset.skillTitle || slug,
    when: btn.dataset.skillWhen || "",
    description: btn.dataset.skillDesc || "",
  };
}

export function initSkillPopover(): void {
  const dialog = document.querySelector<HTMLDialogElement>("#skill-dialog");
  if (!dialog || typeof dialog.showModal !== "function") {
    // Old browser without <dialog> support. Buttons stay buttons but
    // the popover never opens — graceful no-op rather than throw.
    return;
  }

  const titleEl = dialog.querySelector<HTMLElement>("[data-dialog-title]");
  const slugEl = dialog.querySelector<HTMLElement>("[data-dialog-slug]");
  const whenEl = dialog.querySelector<HTMLElement>("[data-dialog-when]");
  const descEl = dialog.querySelector<HTMLElement>("[data-dialog-desc]");
  const closeBtn = dialog.querySelector<HTMLButtonElement>("[data-dialog-close]");

  let lastTrigger: HTMLElement | null = null;

  function open(btn: HTMLElement) {
    const payload = readPayload(btn);
    if (!payload || !dialog) return;
    if (titleEl) titleEl.textContent = payload.title;
    if (slugEl) slugEl.textContent = payload.slug;
    if (whenEl) whenEl.textContent = payload.when;
    if (descEl) descEl.textContent = payload.description;
    btn.setAttribute("aria-expanded", "true");
    lastTrigger = btn;
    dialog.showModal();
    // Move focus to the close button so screen-reader announcement
    // lands on the dialog. The dialog itself isn't programmatically
    // focusable cross-browser; the close button is the safe target.
    closeBtn?.focus();
  }

  function close() {
    if (!dialog) return;
    if (dialog.open) dialog.close();
  }

  // Wire every skill-chip button.
  document.querySelectorAll<HTMLButtonElement>("[data-skill-slug]").forEach((btn) => {
    btn.addEventListener("click", () => open(btn));
  });

  // Backdrop click closes. The click target is the dialog element
  // itself when the user clicks outside the inner content (the inner
  // panel stops propagation via being a descendant; we check rect).
  dialog.addEventListener("click", (e) => {
    if (e.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    const inDialog =
      e.clientX >= rect.left &&
      e.clientX <= rect.right &&
      e.clientY >= rect.top &&
      e.clientY <= rect.bottom;
    if (!inDialog) close();
  });

  closeBtn?.addEventListener("click", () => close());

  // On close (ESC, backdrop, close-button), restore aria-expanded and
  // focus to the trigger.
  dialog.addEventListener("close", () => {
    if (lastTrigger) {
      lastTrigger.setAttribute("aria-expanded", "false");
      lastTrigger.focus();
      lastTrigger = null;
    }
  });
}
