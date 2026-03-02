/**
 * Injects a visible mouse pointer into the page for demo recordings.
 *
 * Playwright video doesn't capture the OS cursor, so this renders an
 * SVG arrow (macOS-style) that follows mousemove events. Sized relative
 * to the 1280×720 recording viewport.
 *
 * Also provides helpers for smooth mouse movement, clicking, and
 * scrolling so demos don't look robotic.
 */
import type { Locator, Page } from "@playwright/test";

// macOS-style arrow cursor as inline SVG — white fill, dark border
const CURSOR_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 28 28">
  <path d="M2 2 L2 24 L8.5 17.5 L14 26 L18 24 L12.5 15.5 L22 15.5 Z"
        fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
</svg>`.trim();

let currentX = 0;
let currentY = 0;

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

  // Park the cursor at center-top so the first move looks natural
  currentX = 640;
  currentY = 100;
  await page.mouse.move(currentX, currentY);
}

/**
 * Smoothly move the mouse from its current position to the center of
 * the target locator. Uses page.mouse.move with `steps` to generate
 * intermediate mousemove events that the injected cursor follows.
 */
export async function moveTo(locator: Locator): Promise<void> {
  const box = await locator.boundingBox();
  if (!box) return;
  const targetX = box.x + box.width / 2;
  const targetY = box.y + box.height / 2;
  const page = locator.page();
  await page.mouse.move(targetX, targetY, { steps: 25 });
  currentX = targetX;
  currentY = targetY;
}

/**
 * Smoothly move to a locator then click it.
 */
export async function click(locator: Locator): Promise<void> {
  await moveTo(locator);
  const page = locator.page();
  await page.mouse.down();
  await page.waitForTimeout(80);
  await page.mouse.up();
}

/**
 * Smooth-scroll a locator into view instead of the instant jump
 * that scrollIntoViewIfNeeded produces.
 */
export async function smoothScroll(locator: Locator): Promise<void> {
  await locator.evaluate((el) => {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  await locator.page().waitForTimeout(600);
}
