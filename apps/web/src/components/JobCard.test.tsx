import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { JobCard } from "./JobCard";

it("renders job and fires onAction on Save", async () => {
  const onAction = vi.fn();
  render(
    <JobCard action="save" onAction={onAction}
      job={{ source: "ashby", company: "Ramp", title: "FDE", location: "SF",
             url: "https://x", score: 90, reason: "great" }} />,
  );
  expect(screen.getByText("FDE")).toBeInTheDocument();
  expect(screen.getByText("90")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  expect(onAction).toHaveBeenCalledOnce();
});
