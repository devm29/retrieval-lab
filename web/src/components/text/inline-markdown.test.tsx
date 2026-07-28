import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InlineMarkdown } from "./inline-markdown";

function html(text: string): string {
  return render(<InlineMarkdown text={text} />).container.innerHTML;
}

describe("InlineMarkdown", () => {
  it("renders emphasis and strong without the asterisks", () => {
    expect(html("A *very* **bold** claim")).toBe("A <em>very</em> <strong class=\"font-semibold\">bold</strong> claim");
  });

  it("drops heading markers at the start of a line", () => {
    expect(html("## Lecture I\nThe candle")).toBe("Lecture I\nThe candle");
  });

  it("leaves arithmetic and unpaired asterisks alone", () => {
    expect(html("2 * 3 * 4 and a stray *")).toBe("2 * 3 * 4 and a stray *");
  });
});
