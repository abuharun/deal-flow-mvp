import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { PageHeader } from "@/components/PageHeader";
import { ProgressBar } from "@/components/ProgressBar";
import { StatusBadge } from "@/components/StatusBadge";
import { getRuns, getSchedules } from "@/lib/data";

const subjects = [
  { name: "Mechanical Engineering", universities: 412, programmes: 1186, values: [78, 71, 64, 52, 59] },
  { name: "Computer Science", universities: 455, programmes: 1302, values: [81, 74, 69, 48, 63] },
  { name: "Civil Engineering", universities: 301, programmes: 904, values: [62, 58, 51, 37, 44] },
];

const attention = [
  ["6", "Failed sites", "Tsinghua University — HTTP 403", "coral"],
  ["12", "Provenance violations", "Value without a source", "peach"],
  ["9", "Conflicts", "ETH Zurich — two official pages", "coral"],
  ["47", "Changed by last re-run", "old → new values need approval", "ochre"],
] as const;

export default function Dashboard() {
  const runs = getRuns();
  const schedules = getSchedules();

  return (
    <AppShell>
      <PageHeader
        title="Dashboard"
        eyebrow="Saturday, 10 Oct 2026"
        actions={<><Link className="btn secondary" href="/import">Import workbook</Link><Link className="btn primary" href="/runs/new">New run</Link></>}
      />
      <div className="grid4">
        {[["Universities", "486", "across 3 subjects"], ["Programmes", "3,392", "1,804 Bachelor · 1,588 Master"], ["Stale values", "228", "older than 12 months"], ["Awaiting review", "74", "47 changed by last re-run"]].map((item) => (
          <div className="kpi" key={item[0]}><span className="kpi-label">{item[0]}</span><strong>{item[1]}</strong><small>{item[2]}</small></div>
        ))}
      </div>
      <div className="grid2 dashboard-primary">
        <section className="card">
          <div className="cardhead"><h2>Completeness by subject</h2><span className="muted small">% with a sourced value or “Not found”</span></div>
          {subjects.map((subject) => (
            <div className="completeness-row" key={subject.name}>
              <b>{subject.name}</b><span>{subject.universities}</span><span>{subject.programmes}</span>
              {subject.values.map((value, index) => <ProgressBar key={index} value={value} label={`${value}%`} />)}
            </div>
          ))}
          <div className="pillrow status-summary"><b>Research status</b><StatusBadge>Pending</StatusBadge> 1,204 <StatusBadge>Researched</StatusBadge> 1,872 <StatusBadge>Needs recheck</StatusBadge> 316</div>
        </section>
        <section className="card">
          <div className="cardhead"><h2>Needs attention</h2><span className="muted small">74 items</span></div>
          {attention.map((item) => (
            <div className="attention-row" key={item[1]}>
              <b style={{ background: `var(--${item[3]})` }}>{item[0]}</b>
              <span><strong>{item[1]}</strong><small className="muted">{item[2]}</small></span>
              <Link className="btn text" href="/review/R-0142">{item[1].startsWith("Changed") ? "Review changes" : "Review"}</Link>
            </div>
          ))}
        </section>
      </div>
      <div className="grid2 dashboard-secondary">
        <section className="card">
          <div className="cardhead"><h2>Upcoming scheduled runs</h2><Link href="/schedules">Schedules</Link></div>
          {schedules.slice(0, 3).map((schedule) => <div className="schedule-summary" key={schedule.id}><span><b>{schedule.name}</b><small className="muted">{schedule.scope}</small></span><b>{schedule.nextRun}</b></div>)}
        </section>
        <section className="card">
          <div className="cardhead"><h2>Recent runs</h2><span className="muted small">All runs</span></div>
          <div className="recent-runs" aria-label="Recent runs">
            {runs.map((run) => <div className="recent-run" key={run.id}><span className="mono">{run.id}</span><span>{run.type}</span><span>{run.scope}</span><span>{run.started}</span><StatusBadge>{run.status}</StatusBadge></div>)}
          </div>
        </section>
      </div>
    </AppShell>
  );
}
