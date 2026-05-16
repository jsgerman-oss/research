// User preferences: which trio is active, which mode (light/dark/cb). Single
// owner of localStorage keys + DOM <html data-*> attribute writes + pub/sub so
// components can react to changes without each maintaining its own
// MutationObserver or storage-key incantation.
//
// Initial state is read from the DOM (set by the preflight script in
// app.html, which runs before this module is imported). The preflight stays
// as inline JS because it must run before CSS paints — it can't depend on a
// module load. This module just trusts the DOM as its own startup oracle.

import { isTrioName, type TrioName } from '$lib/themes/manifest';

export type Mode = 'light' | 'dark' | 'cb';
export type Prefs = { trio: TrioName; mode: Mode };

const TRIO_KEY = 'jody-trio';
const MODE_KEY = 'jody-mode';
const MODES: readonly Mode[] = ['light', 'dark', 'cb'] as const;

const isMode = (m: unknown): m is Mode => typeof m === 'string' && (MODES as readonly string[]).includes(m);

let currentTrio: TrioName = 'coastal-calm';
let currentMode: Mode = 'light';

if (typeof document !== 'undefined') {
  const t = document.documentElement.dataset.theme;
  if (t && isTrioName(t)) currentTrio = t;
  const m = document.documentElement.dataset.mode;
  if (isMode(m)) currentMode = m;
}

const subscribers = new Set<(prefs: Prefs) => void>();

function notify() {
  const snapshot: Prefs = { trio: currentTrio, mode: currentMode };
  for (const cb of subscribers) cb(snapshot);
}

function safeWrite(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch (_err) {
    // localStorage unavailable; in-memory + DOM still update.
  }
}

export function getTrio(): TrioName {
  return currentTrio;
}

export function setTrio(name: TrioName): void {
  if (!isTrioName(name) || name === currentTrio) return;
  currentTrio = name;
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = name;
  }
  safeWrite(TRIO_KEY, name);
  notify();
}

export function getMode(): Mode {
  return currentMode;
}

export function setMode(mode: Mode): void {
  if (!isMode(mode) || mode === currentMode) return;
  currentMode = mode;
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.mode = mode;
  }
  safeWrite(MODE_KEY, mode);
  notify();
}

/**
 * Subscribe to preference changes. Calls `cb` synchronously with the current
 * snapshot, then again whenever trio or mode changes. Returns an unsubscribe
 * function.
 */
export function subscribe(cb: (prefs: Prefs) => void): () => void {
  subscribers.add(cb);
  cb({ trio: currentTrio, mode: currentMode });
  return () => {
    subscribers.delete(cb);
  };
}
