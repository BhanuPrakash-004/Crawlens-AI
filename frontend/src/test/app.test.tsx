import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import { issuesCsv } from "../lib";
import sample from "./fixtures/report.json";
import type { Issue } from "../types";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/health")
        return {
          ok: true,
          json: async () => ({
            status: "ok",
            crawler_configured: false,
            ai_configured: false,
            model: "test",
            page_limit: 20,
            link_limit: 300,
          }),
        };
      if (url.startsWith("/api/audits?"))
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                audit_id: "saved",
                website: sample.website,
                created_at: sample.completed_at,
                status: "completed",
                score: 78,
                pages: 12,
                issues: 17,
              },
            ],
            total: 1,
          }),
        };
      return {
        ok: true,
        json: async () => ({
          status: "completed",
          report: { ...sample, is_sample: false },
          audit_id: "saved",
        }),
      };
    }),
  );
});

describe("Crawlens workspace", () => {
  it("starts empty without fetching sample data", async () => {
    render(<App />);
    expect(
      await screen.findByRole("button", { name: "View audit history" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Sample audit")).not.toBeInTheDocument();
    expect(
      vi
        .mocked(fetch)
        .mock.calls.every(([url]) => !String(url).includes("sample")),
    ).toBe(true);
  });
  it("drills into metric findings and filters by search", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "View audit history" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Open audit for/ }),
    );
    await screen.findByText("Saved audit");
    await user.click(
      screen.getByRole("button", { name: "View Metadata findings" }),
    );
    expect(
      screen.getByRole("heading", {
        name: "All findings",
      }),
    ).toBeInTheDocument();
    await user.type(
      screen.getByRole("textbox", { name: "Search issues" }),
      "not-a-matching-page",
    );
    expect(await screen.findByText("No matching findings")).toBeInTheDocument();
  });
  it("opens page evidence and scoring rules in accessible dialogs", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "View audit history" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Open audit for/ }),
    );
    await screen.findByText("Saved audit");
    await user.click(screen.getByRole("button", { name: "Analyzed pages" }));
    await user.click(screen.getByRole("button", { name: "Inspect page /" }));
    expect(
      screen.getByRole("dialog", { name: "Page evidence" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("dialog", { name: "Page evidence" })).getAllByText(
        /Home — Northstar/,
      )[0],
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close dialog" }));
    await user.click(screen.getByRole("button", { name: "Scoring guide" }));
    expect(
      screen.getByRole("dialog", { name: "A score you can explain" }),
    ).toBeInTheDocument();
  });
  it("submits normalized URLs and surfaces background job failure", async () => {
    const user = userEvent.setup();
    const base = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        if (url === "/api/audits") {
          expect(JSON.parse(String(options?.body))).toEqual({
            url: "https://example.com",
          });
          return {
            ok: true,
            json: async () => ({ audit_id: "test", status: "queued" }),
          };
        }
        if (url === "/api/audits/test")
          return {
            ok: true,
            json: async () => ({
              audit_id: "test",
              status: "failed",
              stage: "failed",
              error: "Firecrawl is not configured.",
              report: null,
            }),
          };
        return base(url, options);
      }),
    );
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "View audit history" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Open audit for/ }),
    );
    await screen.findByText("Saved audit");
    await user.type(
      screen.getByRole("textbox", { name: "Website URL" }),
      "example.com",
    );
    await user.click(screen.getByRole("button", { name: "Analyze website" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Firecrawl is not configured.",
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Analyze website" }),
      ).toBeEnabled(),
    );
  });
  it("exports saved report with a visible format choice", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "View audit history" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Open audit for/ }),
    );
    await screen.findByText("Saved audit");
    await user.click(screen.getByRole("button", { name: "Export report" }));
    const modal = screen.getByRole("dialog", {
      name: "Take your insights with you",
    });
    expect(
      within(modal).getByText("Complete audit report"),
    ).toBeInTheDocument();
    expect(within(modal).getByText("Page-level issues")).toBeInTheDocument();
  });
  it("shows rule-based recommendations and navigates to evidence", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      await screen.findByRole("button", { name: "View audit history" }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Open audit for/ }),
    );
    await screen.findByText("Saved audit");
    await user.click(screen.getByRole("button", { name: "Action plan" }));
    expect(screen.getByText("Rule-based plan")).toBeInTheDocument();
    await user.click(
      screen.getAllByRole("button", { name: /View \d+ linked finding/ })[0],
    );
    expect(
      screen.getByText("Showing evidence for the selected recommendation"),
    ).toBeInTheDocument();
  });
});

it("shows robots permissions, sitemap URLs, and discovered social sources", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    await screen.findByRole("button", { name: "View audit history" }),
  );
  await user.click(
    await screen.findByRole("button", { name: /Open audit for/ }),
  );
  await screen.findByText("Saved audit");
  await user.click(screen.getByRole("button", { name: "Site essentials" }));
  expect(
    screen.getByRole("heading", { name: "Inside your robots.txt" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Disallow: \/admin\//)).toBeInTheDocument();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Select search crawler" }),
    "Bingbot",
  );
  expect(screen.getAllByText("Allowed")).toHaveLength(12);
  expect(
    screen.getByText(/Valid URL sitemap with 12 entries/),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Social presence" }));
  expect(
    screen.getByRole("heading", { name: "4 social profiles. One website." }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Open LinkedIn profile" }),
  ).toHaveAttribute("href", "https://linkedin.com/company/northstar-demo");
  expect(screen.getAllByText("JSON-LD sameAs")).toHaveLength(2);
});

it("escapes CSV and prevents spreadsheet formula injection", () => {
  const issue = {
    ...sample.issues[0],
    observed: '=HYPERLINK("evil")',
    expected: "line one\nline two",
  } as Issue;
  const csv = issuesCsv([issue]);
  expect(csv).toContain('"\'=HYPERLINK(""evil"")"');
  expect(csv).toContain('"line one\nline two"');
});
