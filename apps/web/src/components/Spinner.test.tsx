import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import { Spinner } from "./Spinner";

it("renders a loading status indicator", () => {
  render(<Spinner />);
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
});
