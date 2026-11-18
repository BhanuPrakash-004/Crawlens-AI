"""Print the RESULTS.md tables from a saved audit, so no number is copied by hand.

Usage: .venv/Scripts/python.exe scripts/results_tables.py docs/results-audit.json
Accepts either the report JSON (dashboard export) or the full GET /api/audits/{id} response.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.schemas import Report  # noqa: E402


def cell(value) -> str:
    return str(value).replace('|', '\\|').replace('\n', ' ') if value not in (None, '') else '—'


def main(path: str) -> None:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows consoles default to cp1252
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    report = Report.model_validate(data.get('report', data))
    c = report.coverage

    print('## Audit summary\n')
    print('| Item | Value |\n| --- | --- |')
    for label, value in [
        ('Website', report.website), ('Completed', report.completed_at[:19].replace('T', ' ') + ' UTC'),
        ('Duration', f'{report.duration_seconds} s'), ('Rule version', report.rule_version),
        ('Pages analyzed / failed / limit', f'{c.pages_analyzed} / {c.pages_failed} / {c.page_limit}'),
        ('Internal link destinations: found / verified / unverified', f'{c.links_discovered} / {c.links_verified} / {c.links_unknown}'),
        ('Overall SEO score', f'**{report.overall_score if report.overall_score is not None else "unknown"}/100 · {report.classification}**'),
        ('Score status · coverage', f'{report.score_status} · {c.measured_weight}% of weight measured'),
        ('Action plan source', f'{report.recommendation_source} ({report.recommendation_note})'),
    ]:
        print(f'| {label} | {cell(value)} |')

    print('\n## The six metrics\n')
    print('| # | Metric | Weight | Score | Underlying checks (passed / evaluated) |\n| --- | --- | ---: | ---: | --- |')
    for i, g in enumerate(report.metric_groups, 1):
        checks = ', '.join(f"{n} {report.metrics[n].passing}/{report.metrics[n].evaluated}" for n in g['checks'])
        score = g['score'] if g['score'] is not None else 'unmeasured'
        print(f"| {i} | {g['label']} | {g['weight']}% | {score} | {checks} |")

    print('\n## Metric 1 · Title and meta description, per page\n')
    print('| Page | Title (chars) | Description (chars) | Pass |\n| --- | ---: | ---: | :---: |')
    for page in report.pages:
        d = page.checks['metadata'].details
        title = f"{d.get('title_length', 0)}" if d.get('title_present', True) else 'missing'
        desc = f"{d.get('description_length', 0)}" if d.get('description_present', True) else 'missing'
        mark = {True: 'Pass', False: 'Fail'}.get(page.checks['metadata'].passed, 'Review')
        print(f'| {cell(page.url)} | {title} | {desc} | {mark} |')

    print('\n## Metric 2 · Broken internal links\n')
    broken = [link for link in report.links if link.status == 'broken']
    if not broken:
        print(f'No confirmed broken internal links among {c.links_verified} verified destinations.')
    else:
        print('| Broken URL | HTTP | Found on |\n| --- | ---: | --- |')
        for link in broken:
            print(f"| {cell(link.url)} | {link.status_code} | {cell(', '.join(link.source_pages))} |")

    print('\n## Prioritised action list\n')
    for i, rec in enumerate(report.recommendations, 1):
        print(f"{i}. **[{rec.priority}] {rec.action.rstrip('.')}.** {rec.suggested_fix}")

    if c.warnings or c.failures:
        print('\n## Coverage notes\n')
        for warning in c.warnings:
            print(f'- {warning}')
        for failure in c.failures:
            print(f'- Not analyzed: {failure.url} ({failure.reason})')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
