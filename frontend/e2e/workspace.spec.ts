import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";
import type { Page } from "@playwright/test";
async function openSaved(page: Page, custom?: any) {
  const report =
    custom ??
    JSON.parse(
      await fs.readFile("frontend/src/test/fixtures/report.json", "utf8"),
    );
  report.is_sample = false;
  await page.route("**/api/audits?*", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            audit_id: "fixture",
            website: report.website,
            created_at: report.completed_at,
            status: "completed",
            score: report.overall_score,
            pages: report.pages_crawled,
            issues: report.issues.length,
          },
        ],
        total: 1,
      },
    }),
  );
  await page.route("**/api/audits/fixture", (route) =>
    route.fulfill({
      json: { audit_id: "fixture", status: "completed", report },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "View audit history" }).click();
  await page.getByRole("button", { name: /Open audit for/ }).click();
  await expect(page.getByText("Saved audit", { exact: true })).toBeVisible();
}

test("saved workspace, issue evidence, action plan, exports, and responsive layout", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await openSaved(page);
  await expect(
    page.getByRole("img", { name: "SEO health score: 78 out of 100" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your website. A clearer picture." }),
  ).toBeVisible();
  await page.screenshot({
    path: `artifacts/${testInfo.project.name}-overview.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "View Metadata findings" }).click();
  await expect(
    page.getByRole("heading", { name: "All findings" }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "Search issues" }).fill("/features");
  await expect(
    page.getByRole("table").getByText("/features", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "View issue issue_1", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "A closer look" }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog").getByText("Observed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Action plan", exact: true }).click();
  await expect(
    page.getByText("Rule-based plan", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /View \d+ linked finding/ })
    .first()
    .click();
  await expect(
    page.getByText("Showing evidence for the selected recommendation"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Export report", exact: true })
    .click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /Complete audit report/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain(".json");
  const downloaded = JSON.parse(
    await fs.readFile((await download.path())!, "utf-8"),
  );
  expect(downloaded.is_sample).toBe(false);
  expect(downloaded.overall_score).toBe(78);
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Audit coverage", exact: true })
    .click();
  await expect(
    page.getByText("Unverified destinations", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("audit submission, progress, completion, and error recovery", async ({
  page,
}) => {
  let polls = 0;
  const fixture = JSON.parse(
    await fs.readFile("frontend/src/test/fixtures/report.json", "utf-8"),
  );
  fixture.is_sample = false;
  fixture.website = "https://example.com/";
  fixture.duration_seconds = 1.5;
  // Provider and network outcomes are controlled; this is not a live crawl.
  await page.route("**/api/audits", (route) =>
    route.fulfill({
      status: 202,
      json: { audit_id: "e2e-job", status: "queued" },
    }),
  );
  await page.route("**/api/audits/e2e-job", (route) => {
    polls++;
    return route.fulfill({
      json:
        polls < 2
          ? {
              audit_id: "e2e-job",
              website: "https://example.com/",
              status: "running",
              stage: "verifying_links",
              report: null,
              error: null,
            }
          : {
              audit_id: "e2e-job",
              website: "https://example.com/",
              status: "completed",
              stage: "completed",
              report: fixture,
              error: null,
            },
    });
  });
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Website URL" })
    .fill("https://example.com/");
  await page
    .getByRole("button", { name: "Analyze website", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Audit in progress" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("heading", { name: "Checking links and site essentials" }),
  ).toBeVisible();
  await expect(page.getByText("Saved audit", { exact: true })).toBeVisible();
  await expect(page.getByText("Sample audit", { exact: true })).toHaveCount(0);
  await page.route("**/api/audits", (route) =>
    route.fulfill({
      status: 400,
      json: {
        detail:
          "Enter a public website. Local and private addresses are not allowed.",
      },
    }),
  );
  await page
    .getByRole("textbox", { name: "Website URL" })
    .fill("http://localhost");
  await page
    .getByRole("button", { name: "Analyze website", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Local and private addresses are not allowed.",
  );
  await expect(
    page.getByRole("button", { name: "Analyze website", exact: true }),
  ).toBeEnabled();
});

test("site essentials and social profile evidence work on every viewport", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await openSaved(page);
  async function navigate(name: string) {
    if (testInfo.project.name === "mobile")
      await page.getByRole("button", { name: "Open navigation" }).click();
    await page.getByRole("button", { name, exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  if (testInfo.project.name === "mobile") {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.locator(".mobile-close")).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(
      page.getByRole("button", { name: "Settings", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("button", { name: "Open navigation" }),
    ).toBeFocused();
  }
  await navigate("Site essentials");
  await expect(
    page.getByRole("heading", { name: "Make your website discoverable." }),
  ).toBeFocused();
  await expect(
    page.getByRole("heading", { name: "Inside your robots.txt" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Select search crawler" })
    .selectOption("Bingbot");
  await expect(page.getByText("Allowed", { exact: true })).toHaveCount(12);
  await page.getByText("Discovered URLs", { exact: false }).last().click();
  await expect(page.locator(".sitemap-details .url-list a")).toHaveCount(12);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `artifacts/${testInfo.project.name}-essentials.png`,
    fullPage: true,
  });
  await navigate("Social presence");
  await expect(
    page.getByRole("heading", { name: "4 social profiles. One website." }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open LinkedIn profile" }),
  ).toHaveAttribute("href", "https://linkedin.com/company/northstar-demo");
  const linkedin = page.locator(".social-card").filter({
    has: page.getByRole("heading", { name: "LinkedIn", exact: true }),
  });
  await linkedin.locator("summary").click();
  await expect(linkedin.locator(".url-list a")).toHaveCount(12);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `artifacts/${testInfo.project.name}-social.png`,
    fullPage: true,
  });
  await navigate("Analyzed pages");
  await page
    .getByRole("button", { name: "Inspect page /", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Page evidence" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("unverified supplemental checks are never shown as passing", async ({
  page,
}, testInfo) => {
  const report = JSON.parse(
    await fs.readFile("frontend/src/test/fixtures/report.json", "utf8"),
  );
  report.site_checks.robots_txt = {
    ...report.site_checks.robots_txt,
    status: "unknown",
    status_code: null,
    content: "",
    permissions: [],
    summary: "robots.txt could not be reached.",
  };
  report.site_checks.sitemap = {
    ...report.site_checks.sitemap,
    status: "unknown",
    files: [],
    url_sample: [],
    urls_discovered: 0,
    scanned_pages_listed: 0,
    summary: "Sitemap verification is incomplete.",
  };
  report.site_checks.social = {
    status: "not_found",
    profiles: [],
    pages_checked: 12,
    pages_with_profiles: 0,
    summary: "No supported social profile links were found.",
  };
  await openSaved(page, report);
  await expect(page.getByText("Review", { exact: true })).toHaveCount(2);
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Social presence", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "No social profiles found" }),
  ).toBeVisible();
});

test("empty workspace and laptop sidebar fit without scrolling", async ({
  page,
}, testInfo) => {
  if (testInfo.project.name !== "desktop") return;
  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1280, height: 720 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "View audit history" }),
    ).toBeVisible();
    expect(
      await page
        .locator(".sidebar")
        .evaluate((el) => el.scrollHeight <= el.clientHeight),
    ).toBe(true);
    await expect(
      page.getByRole("button", { name: "Settings", exact: true }),
    ).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `artifacts/laptop-${viewport.width}.png`,
      fullPage: true,
    });
  }
});

test("current report explains score coverage and multiple H1 findings", async ({ page }) => {
  const report = JSON.parse(await fs.readFile("frontend/src/test/fixtures/report.json", "utf8"));
  const weights = {metadata:12,broken_links:12,indexability:16,performance:13,headings:8,site_health:7,canonical:10,structured_data:10,media:7,geo:5};
  report.metrics = Object.fromEntries(Object.entries(weights).map(([key, weight]) => [key, {
    weight, score:key === "headings" ? 100 : null, evaluated:key === "headings" ? 1 : 0,
    passing:key === "headings" ? 1 : 0, unknown:key === "headings" ? 0 : 1, status:key === "headings" ? "measured" : "unknown"
  }]));
  report.overall_score=100;
  report.score_status="partial";
  report.rule_version="3.0";
  report.coverage.measured_weight=8;
  report.executive_summary="Heading structure was verified on the product page.";
  report.issues=[{...report.issues[0], metric:"headings", severity:"low", outcome:"Warning", title:"Review heading structure",
    evidence:{headings:[{position:1,level:"H1",text:"Travel mug",source:"Raw HTML",flags:[]},
                         {position:2,level:"H1",text:"Shipping details",source:"Rendered snapshot only",flags:[]}]}}];
  await openSaved(page,report);
  await expect(page.getByText(report.executive_summary)).toBeVisible();
  await expect(page.getByText("10 metrics · 1 measured")).toBeVisible();
  await page.getByRole("button",{name:"How your score is calculated"}).click();
  await expect(page.getByText(/100 × \(1\/1 × 8\) \/ 8 ≈ 100/)).toBeVisible();
  await page.getByRole("button",{name:"Close dialog"}).click();
  await page.getByRole("button",{name:"View Headings findings"}).click();
  await page.getByRole("button",{name:`View issue ${report.issues[0].id}`}).click();
  await expect(page.getByRole("cell",{name:"Shipping details"})).toBeVisible();
  await expect(page.getByRole("cell",{name:"Rendered snapshot only"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
