import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ConfirmModal } from "./ConfirmModal.jsx";

describe("ConfirmModal", () => {
  it("does not call onConfirm until the confirm button is clicked", () => {
    const onConfirm = vi.fn();
    render(<ConfirmModal open title="Remove member?" onConfirm={onConfirm} onCancel={() => {}} />);
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when closed", () => {
    render(<ConfirmModal open={false} title="x" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.queryByText("x")).not.toBeInTheDocument();
  });
});