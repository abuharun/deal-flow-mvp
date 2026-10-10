"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PageHeader } from "@/components/PageHeader";
import { ActionButton } from "@/components/Toast";

function Check({
  label,
  initial = true,
}: {
  label: string;
  initial?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <input
        type="checkbox"
        checked={value}
        onChange={(event) => setValue(event.target.checked)}
      />
      {label}
    </label>
  );
}
function OptionToggle({ label, initial }: { label: string; initial: boolean }) {
  const [value, setValue] = useState(initial);
  return (
    <button
      type="button"
      className={`toggle ${value ? "on" : ""}`}
      aria-label={label}
      aria-pressed={value}
      onClick={() => setValue((current) => !current)}
    >
      <i />
    </button>
  );
}

export default function Page() {
  const [maxPages, setMaxPages] = useState("40");
  return (
    <AppShell>
      <PageHeader
        title="New run"
        eyebrow={'From Universities · filter "QS 1–150, ME + CS" · 42 selected'}
      />
      <div className="grid2" style={{ gridTemplateColumns: "1.6fr .9fr" }}>
        <div className="stack">
          <section className="card">
            <div className="cardhead">
              <h2>Selection</h2>
              <ActionButton className="btn text">Edit selection</ActionButton>
            </div>
            <div className="pillrow">
              {[
                "Massachusetts Institute of Technology",
                "ETH Zurich",
                "The University of Queensland",
                "Tsinghua University",
                "Delft University of Technology",
                "+ 37 more",
              ].map((item) => (
                <span className="badge gray" key={item}>
                  {item}
                </span>
              ))}
            </div>
            <p className="small" style={{ color: "#7a5200" }}>
              2 universities have no official website and will be skipped.
            </p>
          </section>
          <div className="grid3">
            <section className="card">
              <h2>Subjects</h2>
              <div className="stack" style={{ gap: 9, marginTop: 13 }}>
                <Check label="Mechanical Engineering" />
                <Check label="Computer Science" />
                <Check label="Civil Engineering" initial={false} />
              </div>
            </section>
            <section className="card">
              <h2>Study level</h2>
              <div className="stack" style={{ gap: 9, marginTop: 13 }}>
                <Check label="Bachelor" />
                <Check label="Master" />
              </div>
            </section>
            <section className="card">
              <h2>Fields to collect</h2>
              <div className="stack" style={{ gap: 9, marginTop: 13 }}>
                {[
                  "Application Deadline",
                  "Tuition Fee (International)",
                  "Entry Requirements",
                  "Scholarships",
                  "Study Subjects",
                ].map((item, index) => (
                  <Check key={item} label={item} initial={index !== 3} />
                ))}
              </div>
            </section>
          </div>
          <section className="card">
            <h2>Options</h2>
            <div className="option-row">
              <label htmlFor="max-pages">Max pages per university</label>
              <input
                id="max-pages"
                className="input"
                style={{ minWidth: 70, width: 70, height: 30 }}
                inputMode="numeric"
                value={maxPages}
                onChange={(event) => setMaxPages(event.target.value)}
              />
            </div>
            {(
              [
                ["Render JavaScript pages", true],
                ["Re-scrape researched rows", false],
                ["Only stale rows", false],
              ] as const
            ).map(([label, initial]) => (
              <div className="option-row" key={label}>
                <span>{label}</span>
                <OptionToggle label={label} initial={initial} />
              </div>
            ))}
          </section>
        </div>
        <aside>
          <section className="card">
            <h2>Job breakdown</h2>
            <Data />
            <hr />
            <p>
              <b>Extraction jobs</b>
              <b style={{ float: "right" }}>153</b>
            </p>
            <p>
              <b>Site crawls</b>
              <b style={{ float: "right" }}>40</b>
            </p>
            <p className="small muted">
              Each university site is crawled once and every selected subject is
              extracted from the same pages.
            </p>
            <p>
              Estimated time <b style={{ float: "right" }}>≈ 2 h 50 min</b>
            </p>
            <p>
              Estimated model cost <b style={{ float: "right" }}>≈ USD 17.90</b>
            </p>
          </section>
          <div className="stack" style={{ gap: 8, marginTop: 12 }}>
            <ActionButton>Start now</ActionButton>
            <ActionButton className="btn secondary">
              Save as schedule
            </ActionButton>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}

function Data() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 45px 45px 45px",
        gap: 8,
        marginTop: 15,
      }}
    >
      <small>SUBJECT</small>
      <small>BACH.</small>
      <small>MAST.</small>
      <small>JOBS</small>
      <b>Mechanical Engineering</b>
      <span>40</span>
      <span>38</span>
      <b>78</b>
      <b>Computer Science</b>
      <span>40</span>
      <span>35</span>
      <b>75</b>
    </div>
  );
}
