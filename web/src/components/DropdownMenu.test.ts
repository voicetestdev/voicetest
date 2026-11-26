import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import { createRawSnippet } from "svelte";
import DropdownMenu from "./DropdownMenu.svelte";

const trigger = createRawSnippet((toggle: () => () => void) => ({
  render: () => "<button>Open menu</button>",
  setup: (node: Element) => {
    node.addEventListener("click", () => toggle()());
  },
}));

const items = createRawSnippet(() => ({
  render: () =>
    "<div><li><button>First</button></li><li><button disabled>Unavailable</button></li></div>",
}));

function renderMenu() {
  render(DropdownMenu, { props: { trigger, children: items } });
  return screen.getByRole("button", { name: "Open menu" });
}

describe("DropdownMenu", () => {
  afterEach(() => cleanup());

  it("opens on trigger click and closes when an item is chosen", async () => {
    const openButton = renderMenu();
    expect(screen.queryByRole("menu")).toBeNull();

    await fireEvent.click(openButton);
    expect(screen.getByRole("menu")).toBeDefined();

    await fireEvent.click(screen.getByRole("button", { name: "First" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("stays open when a disabled item is clicked", async () => {
    await fireEvent.click(renderMenu());

    await fireEvent.click(screen.getByRole("button", { name: "Unavailable" }));

    expect(screen.getByRole("menu")).toBeDefined();
  });

  it("closes on an outside click or Escape", async () => {
    const openButton = renderMenu();

    await fireEvent.click(openButton);
    await fireEvent.click(document.body);
    expect(screen.queryByRole("menu")).toBeNull();

    await fireEvent.click(openButton);
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
