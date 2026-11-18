import type { Check, MetricKey } from "../types";

export function outcome(check?: Check) {
  if (check?.outcome) return check.outcome;
  if (check?.details.not_applicable) return "N/A";
  if (check?.passed === false) return "Failed";
  if (Array.isArray(check?.details.warnings) && check.details.warnings.length) return "Warning";
  return check?.passed === true ? "Passed" : "Review";
}

export function MeasuredEvidence({metric, data}: {metric: MetricKey | string; data?: Record<string, unknown>}) {
  if (!data) return null;
  if (metric === "headings" && Array.isArray(data.headings)) {
    return <div className="table-scroll"><table><caption>Headings in document order</caption>
      <thead><tr><th>Position</th><th>Level</th><th>Heading text</th><th>Source</th><th>Observation</th></tr></thead>
      <tbody>{data.headings.map((row,i)=><tr key={i}><td>{row.position}</td><td>{row.level}</td><td>{row.text || "(empty)"}</td><td>{row.source}</td><td>{row.flags.join(", ") || "—"}</td></tr>)}</tbody>
    </table></div>;
  }
  if (metric === "media" && Array.isArray(data.resources)) {
    return <div className="table-scroll"><table><caption>Media on this page</caption>
      <thead><tr><th>Type</th><th>Source</th><th>Alternative or label</th><th>Finding</th></tr></thead>
      <tbody>{data.resources.map((r,i)=><tr key={i}><td>{r.kind}</td><td>{r.url || r.source || "(inline)"}</td><td>{r.alt ?? r.label ?? "Missing"}{r.decorative && " (decorative)"}</td><td>{[...r.failures,...r.reviews].join(" ") || r.resource_status || "Source unverified"}</td></tr>)}</tbody>
    </table></div>;
  }
  if (metric === "broken_links" && Array.isArray(data.references)) {
    return <div className="table-scroll"><table><caption>Referring links</caption><thead><tr><th>Source page</th><th>Original href</th><th>Accessible name</th></tr></thead>
      <tbody>{data.references.map((r,i)=><tr key={i}><td>{r.page_url}</td><td>{r.href}</td><td>{r.text || "(empty)"}</td></tr>)}</tbody></table></div>;
  }
  return null;
}
