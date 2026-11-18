import { useEffect, useState } from "react";
import { Check, LoaderCircle, Radar } from "lucide-react";
import { host } from "../lib";
const stages = [
  {
    key: "queued",
    label: "Starting your audit",
    detail: "Preparing a fresh perspective on your website.",
  },
  {
    key: "crawling",
    label: "Exploring your website",
    detail: "Collecting public pages and source HTML with Firecrawl.",
  },
  {
    key: "verifying_pages",
    label: "Verifying page evidence",
    detail: "Checking response headers and complete HTML against the website.",
  },
  {
    key: "analyzing",
    label: "Connecting the dots",
    detail: "Checking metadata, indexability, headings, and structured data.",
  },
  {
    key: "verifying_links",
    label: "Checking links and site essentials",
    detail: "Verifying destinations, robots.txt rules, and sitemap discovery.",
  },
  {
    key: "generating_recommendations",
    label: "Making it actionable",
    detail: "Turning measured findings into your prioritized action plan.",
  },
];
export function AuditProgress({
  stage,
  website,
}: {
  stage: string;
  website: string;
}) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const current = Math.max(
    0,
    stages.findIndex((item) => item.key === stage),
  );
  return (
    <section className="card progress-card" role="status" aria-live="polite">
      <div className="scan-visual" aria-hidden="true">
        <div />
        <div />
        <Radar size={42} />
      </div>
      <span className="eyebrow">A CLEARER PICTURE IS ON ITS WAY</span>
      <h2>{stages[current].label}</h2>
      <p>{stages[current].detail}</p>
      <span className="scanning-url">
        {host(website)}
        <span className="inline-dot">·</span>
        {seconds}s elapsed in this view
      </span>
      <div className="progress-stages">
        {stages.map((item, index) => (
          <div
            className={
              index === current ? "active" : index < current ? "done" : ""
            }
            key={item.key}
          >
            <span>
              {index < current ? (
                <Check size={14} />
              ) : index === current ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                index + 1
              )}
            </span>
            <p>{item.label}</p>
          </div>
        ))}
      </div>
      <p className="microcopy">
        Audits run in the background. If you refresh, we’ll reconnect to this
        job.
      </p>
    </section>
  );
}
