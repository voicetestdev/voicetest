/**
 * Injects a visible mouse pointer into the page for demo recordings.
 *
 * Playwright video doesn't capture the OS cursor, so this renders an
 * SVG arrow (macOS-style) that follows mousemove events. Sized relative
 * to the 1280×720 recording viewport.
 */
import type { Page } from "@playwright/test";

// macOS-style arrow cursor as inline SVG — white fill, dark border
const CURSOR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
  <path d="M2 2 L2 24 L8.5 17.5 L14 26 L18 24 L12.5 15.5 L22 15.5 Z"
        fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
</svg>`.trim();

export async function installCursor(page: Page): Promise<void> {
  await page.addInitScript((svg: string) => {
    const el = document.createElement("div");
    el.id = "demo-cursor";
    el.innerHTML = svg;
    Object.assign(el.style, {
      position: "fixed",
      zIndex: "999999",
      pointerEvents: "none",
      left: "-100px",
      top: "-100px",
      filter: "drop-shadow(1px 2px 2px rgba(0,0,0,0.35))",
      transition: "transform 0.1s ease-out",
      transform: "scale(1)",
    });

    document.addEventListener("DOMContentLoaded", () => {
      document.body.appendChild(el);
    });

    window.addEventListener("mousemove", (e) => {
      el.style.left = `${e.clientX}px`;
      el.style.top = `${e.clientY}px`;
    });

    window.addEventListener("mousedown", () => {
      el.style.transform = "scale(0.85)";
    });

    window.addEventListener("mouseup", () => {
      el.style.transform = "scale(1)";
    });
  }, CURSOR_SVG);
}
