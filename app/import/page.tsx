"use client";
import { AppShell } from "@/components/AppShell";
import { PageHeader } from "@/components/PageHeader";
import { ActionButton, useToast } from "@/components/Toast";
const files = [
  [
    "QS_2026_Mechanical_Engineering.xlsx",
    "412 KB",
    "Mechanical Engineering",
    "Bachelor (412 rows) · Masters (398 rows)",
  ],
  [
    "QS_2026_Computer_Science.xlsx",
    "455 KB",
    "Computer Science",
    "Bachelor (455) · Masters (447)",
  ],
  [
    "subject_rankings_export (3).xlsx",
    "301 KB",
    "Assign subject…",
    "Bachelor (301) · Masters (287)",
  ],
];
export default function Page() {
  const toast = useToast();
  return (
    <AppShell>
      <PageHeader
        title="Import workbooks"
        eyebrow="QS subject rankings · one workbook per subject · Bachelor + Masters sheets"
        actions={
          <div className="pillrow">
            <span className="badge dark">1 Upload</span>
            <span className="badge dark">2 Map columns</span>
            <span className="badge gray">3 Validate</span>
            <span className="badge outline">4 Summary</span>
          </div>
        }
      />
      <div className="grid2" style={{ gridTemplateColumns: "1fr 300px" }}>
        <section className="card">
          <h2>Files (3)</h2>
          {files.map((f, i) => (
            <div
              key={f[0]}
              style={{
                display: "grid",
                gridTemplateColumns: "1.2fr 190px 1fr 20px",
                gap: 10,
                padding: "12px 0",
                borderBottom: "1px solid #f0f0f0",
                alignItems: "center",
              }}
            >
              <span className="mono">
                <b>{f[0]}</b>
                <small className="muted" style={{ display: "block" }}>
                  {f[1]}
                </small>
              </span>
              <select
                className="input"
                defaultValue={f[2]}
                style={{
                  minWidth: 0,
                  borderColor: i === 2 ? "var(--coral)" : undefined,
                }}
              >
                <option>{f[2]}</option>
              </select>
              <span>{f[3]}</span>
              <button className="iconbtn" type="button" onClick={toast} aria-label={`Remove ${f[0]}`}>
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn secondary"
            onClick={toast}
            style={{ width: "100%", borderStyle: "dashed", marginTop: 12 }}
          >
            Drop more .xlsx files here or browse
          </button>
        </section>
        <section className="card">
          <h2>Validation</h2>
          {[
            ["Duplicates", "4", "“Imperial College London” appears twice."],
            [
              "Missing official website",
              "17",
              "Runs skip these until a URL is added.",
            ],
            ["Unmatched universities", "9", "“Univ. of Queensland” — merge?"],
          ].map((w) => (
            <div
              className="note"
              key={w[0]}
              style={{ border: "1px solid var(--ochre)", marginTop: 10 }}
            >
              <b>
                {w[0]} <span style={{ float: "right" }}>{w[1]}</span>
              </b>
              <p>{w[2]}</p>
              <u>Show all</u>
            </div>
          ))}
        </section>
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <div className="cardhead">
          <h2>Column mapping</h2>
          <div className="pillrow">
            <span className="badge gray">
              QS_2026_Mechanical_Engineering · Bachelor
            </span>
            <span className="badge outline">Masters</span>
            <span className="badge outline">Computer Science…</span>
          </div>
        </div>
        {[
          ["Rank", "QS Rank", "1"],
          [
            "Institution",
            "University",
            "Massachusetts Institute of Technology",
          ],
          ["Location", "Country/Territory", "United States"],
          ["Region", "Region", "North America"],
          ["Website", "Official Website", "https://web.mit.edu"],
          ["(sheet name)", "Study Level", "Bachelor"],
          ["(file)", "Subject", "Mechanical Engineering"],
          ["Overall Score", "— Ignore —", "98.4"],
        ].map((m) => (
          <div
            key={m[0]}
            style={{
              display: "grid",
              gridTemplateColumns: "200px 25px 220px 1fr",
              gap: 10,
              padding: "6px 0",
              alignItems: "center",
            }}
          >
            <span className="mono">{m[0]}</span>
            <span>→</span>
            <select
              className="input"
              defaultValue={m[1]}
              style={{ minWidth: 0 }}
            >
              <option>{m[1]}</option>
            </select>
            <span>{m[2]}</span>
          </div>
        ))}
        <p className="muted small">
          Programme rows are created empty with status Pending and filled by
          runs.
        </p>
      </section>
      <section className="card" style={{ marginTop: 16 }}>
        <div className="cardhead">
          <h2>Result summary</h2>
          <span className="muted small">
            286 universities merge into one university record
          </span>
        </div>
        <div className="grid3">
          {[
            ["Mechanical Engineering", "412", "38", "374", "412 / 398"],
            ["Computer Science", "455", "61", "394", "455 / 447"],
            ["Civil Engineering", "301", "22", "279", "301 / 287"],
          ].map((s) => (
            <div className="note" key={s[0]}>
              <b>{s[0]}</b>
              <p>
                Universities <b style={{ float: "right" }}>{s[1]}</b>
                <br />
                New records <b style={{ float: "right" }}>{s[2]}</b>
                <br />
                Merged <b style={{ float: "right" }}>{s[3]}</b>
                <br />
                Rows Bachelor / Masters <b style={{ float: "right" }}>{s[4]}</b>
              </p>
            </div>
          ))}
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginTop: 12,
          }}
        >
          <ActionButton className="btn secondary">Back</ActionButton>
          <ActionButton disabled>
            Import 3 files — assign subject first
          </ActionButton>
        </div>
      </section>
    </AppShell>
  );
}
