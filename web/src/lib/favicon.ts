/**
 * Dynamic favicon that reflects run status.
 *
 * Swaps the browser tab favicon between pass (green check), fail (red X),
 * running (blue dot), and default (no badge) states. The base icon is the
 * voicetest waveform; only the badge in the bottom-right corner changes.
 */

type FaviconState = "default" | "running" | "pass" | "fail";

const BASE_BARS = `
  <rect x="16" y="30" width="6" height="20" rx="3" fill="#00B4D8"/>
  <rect x="26" y="22" width="6" height="36" rx="3" fill="#00B4D8"/>
  <rect x="36" y="28" width="6" height="24" rx="3" fill="#00B4D8"/>
  <rect x="46" y="18" width="6" height="44" rx="3" fill="#00B4D8"/>
  <rect x="56" y="26" width="6" height="28" rx="3" fill="#00B4D8"/>`;

const BADGES: Record<FaviconState, string> = {
  default: "",
  running: `
    <circle cx="62" cy="58" r="10" fill="#3B82F6"/>
    <circle cx="62" cy="58" r="4" fill="white"/>`,
  pass: `
    <circle cx="62" cy="58" r="10" fill="#22C55E"/>
    <path d="M57 58 L60 61 L67 54" stroke="white" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
  fail: `
    <circle cx="62" cy="58" r="10" fill="#EF4444"/>
    <path d="M58 54 L66 62 M66 54 L58 62" stroke="white" stroke-width="2.5" fill="none" stroke-linecap="round"/>`,
};

function buildSvg(state: FaviconState, size: number): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
  <rect width="80" height="80" rx="16" fill="#1a1a1a"/>${BASE_BARS}${BADGES[state]}
</svg>`;
}

function svgToDataUrl(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

let currentState: FaviconState = "default";

export function setFaviconState(state: FaviconState): void {
  if (state === currentState) return;
  currentState = state;

  const links = document.querySelectorAll<HTMLLinkElement>('link[rel="icon"]');
  for (const link of links) {
    const size = link.sizes?.value === "16x16" ? 16 : 32;
    link.href = svgToDataUrl(buildSvg(state, size));
  }
}

export function resetFavicon(): void {
  setFaviconState("default");
}
