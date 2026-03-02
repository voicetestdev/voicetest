/**
 * Injects a visible cursor dot into the page for demo recordings.
 *
 * Playwright video doesn't capture the OS cursor, so this adds a
 * CSS-styled dot that follows mousemove events and pulses on click.
 */
import type { Page } from "@playwright/test";

export async function installCursor(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const dot = document.createElement("div");
    dot.id = "demo-cursor";
    Object.assign(dot.style, {
      position: "fixed",
      zIndex: "999999",
      pointerEvents: "none",
      width: "20px",
      height: "20px",
      borderRadius: "50%",
      background: "rgba(255, 80, 80, 0.7)",
      boxShadow: "0 0 6px rgba(255, 80, 80, 0.5)",
      transform: "translate(-50%, -50%)",
      transition: "width 0.15s, height 0.15s, background 0.15s",
      left: "-100px",
      top: "-100px",
    });

    document.addEventListener("DOMContentLoaded", () => {
      document.body.appendChild(dot);
    });

    window.addEventListener("mousemove", (e) => {
      dot.style.left = `${e.clientX}px`;
      dot.style.top = `${e.clientY}px`;
    });

    window.addEventListener("mousedown", () => {
      dot.style.width = "28px";
      dot.style.height = "28px";
      dot.style.background = "rgba(255, 40, 40, 0.9)";
    });

    window.addEventListener("mouseup", () => {
      dot.style.width = "20px";
      dot.style.height = "20px";
      dot.style.background = "rgba(255, 80, 80, 0.7)";
    });
  });
}
