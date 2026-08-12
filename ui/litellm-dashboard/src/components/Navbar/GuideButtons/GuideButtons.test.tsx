import { describe, expect, it } from "vitest";
import { renderWithProviders, screen } from "../../../../tests/test-utils";
import { GuideButtons } from "./GuideButtons";

describe("GuideButtons", () => {
  it("should render three guide buttons", () => {
    renderWithProviders(<GuideButtons />);
    expect(screen.getByText("Claude 配置教程")).toBeInTheDocument();
    expect(screen.getByText("Codex 配置教程")).toBeInTheDocument();
    expect(screen.getByText("Workbuddy 配置教程")).toBeInTheDocument();
  });

  it("should open docs in a new tab", () => {
    renderWithProviders(<GuideButtons />);
    const link = screen.getByRole("link", { name: /Claude 配置教程/i });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
