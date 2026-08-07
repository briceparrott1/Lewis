import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { it, expect, vi } from "vitest";
import { CompactJobRow } from "./CompactJobRow";

it("renders job title/company and fires onSave", async () => {
  const onSave = vi.fn();
  render(
    <CompactJobRow
      onSave={onSave}
      job={{ source: "ashby", company: "Ramp", title: "FDE", location: "SF", url: "https://x" }}
    />,
  );
  expect(screen.getByText("FDE")).toBeInTheDocument();
  expect(screen.getByText(/Ramp/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  expect(onSave).toHaveBeenCalledOnce();
});
