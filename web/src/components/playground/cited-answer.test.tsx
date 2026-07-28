import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CitedAnswer } from "./cited-answer";

describe("CitedAnswer", () => {
  it("turns valid markers into buttons and flags unknown ones", () => {
    const onCite = vi.fn();
    render(<CitedAnswer text="Light is fast [1, 2]. Also [9]." validMarkers={new Set([1, 2])} onCite={onCite} />);
    fireEvent.click(screen.getByRole("button", { name: "Source 2" }));
    expect(onCite).toHaveBeenCalledWith(2);
    expect(screen.getByRole("button", { name: "Source 1" })).toBeInTheDocument();
    expect(screen.getByTitle("Citation does not match a source")).toHaveTextContent("[9]");
  });

  it("renders a repeated marker once", () => {
    render(<CitedAnswer text="Twice cited [1, 1]." validMarkers={new Set([1])} onCite={() => undefined} />);
    expect(screen.getAllByRole("button", { name: "Source 1" })).toHaveLength(1);
  });

  it("renders corpus emphasis and keeps markers inside it clickable", () => {
    const { container } = render(
      <CitedAnswer text="The *Chief Justice* presides [1]. *Only cited here [1]*." validMarkers={new Set([1])} onCite={() => undefined} />,
    );
    expect(container).not.toHaveTextContent("*");
    expect(container.querySelector("em")).toHaveTextContent("Chief Justice");
    expect(screen.getAllByRole("button", { name: "Source 1" })).toHaveLength(2);
  });
});
