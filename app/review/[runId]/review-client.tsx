"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PageHeader } from "@/components/PageHeader";
import { StateGate } from "@/components/StateGate";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton } from "@/components/Toast";
import { getProgrammes, getUniversities } from "@/lib/data";

type Mode = "all" | "changes";
const universityIds = ["mit", "imperial", "eth-zurich", "nus", "cambridge", "delft", "tsinghua", "kth", "polimi", "uq", "tum", "kaist", "toronto", "tokyo", "epfl"];
const reviewUniversities = [
  ["uq", "The University of Queensland", "Researched", "2 issues", "ME"],
  ["eth-zurich", "ETH Zurich", "Conflict", "3 issues", "CS"],
  ["cambridge", "University of Cambridge", "Closest equivalent", "1 note", "CE"],
  ["kth", "KTH Royal Institute of Technology", "Changed", "4 changed", "ME"],
  ["mit", "Massachusetts Institute of Technology", "Approved", "0", "CS"],
  ["nus", "National University of Singapore", "Found", "0", "CS"],
  ["tsinghua", "Tsinghua University", "Failed", "site failed", "CE"],
] as const;

export function ReviewClient({ runId, state }: { runId: string; state?: string }) {
  const [mode, setMode] = useState<Mode>("all");
  const [uni, setUni] = useState("uq");
  const [field, setField] = useState("Tuition Fee (International)");
  const [query, setQuery] = useState("");
  const [subject, setSubject] = useState("All");
  const universities = getUniversities();
  const chosen = universities[universityIds.indexOf(uni)] || universities[9];
  const programmes = getProgrammes(uni).slice(0, 2);
  const visibleUniversities = reviewUniversities.filter((item) => item[1].toLowerCase().includes(query.toLowerCase()) && (subject === "All" || item[4] === subject));

  return <AppShell>
    <PageHeader title="Review" eyebrow={`Run ${runId} · Scheduled · 08 Oct 2026`} actions={<><div className="tabs" role="tablist" aria-label="Review mode"><button role="tab" aria-selected={mode === "all"} className={`tab ${mode === "all" ? "active" : ""}`} onClick={() => setMode("all")}>All results</button><button role="tab" aria-selected={mode === "changes"} className={`tab ${mode === "changes" ? "active" : ""}`} onClick={() => setMode("changes")}>Changes since last run · 47</button></div><b>1,212 <span className="muted">approved</span>　74 <span className="muted">to review</span></b></>} />
    <StateGate state={state} kind="review">{mode === "all" ? <div className="reviewlayout">
      <aside className="reviewlist"><label className="sr-only" htmlFor="review-university-search">Filter universities</label><input id="review-university-search" className="input" style={{ width: "100%", minWidth: 0 }} placeholder="Filter universities…" value={query} onChange={(event) => setQuery(event.target.value)} /><div className="pillrow" style={{ margin: "8px 0" }}>{[["All", "All subjects"], ["ME", "ME"], ["CS", "CS"], ["CE", "CE"]].map(([value, label]) => <button type="button" aria-pressed={subject === value} className={`badge ${subject === value ? "dark" : "outline"}`} onClick={() => setSubject(value)} key={value}>{label}</button>)}</div>{visibleUniversities.map((item) => <button className={`reviewuni ${uni === item[0] ? "active" : ""}`} key={item[0]} onClick={() => setUni(item[0])}><b style={{ display: "block" }}>{item[1]}</b><StatusBadge>{item[2]}</StatusBadge><small className="muted" style={{ float: "right" }}>{item[3]}</small></button>)}</aside>
      <section><h2 style={{ fontSize: 20, margin: "0 0 4px" }}>{chosen.name}</h2><p className="muted small">QS #{chosen.qsRank} · {chosen.country} · 41 pages fetched · English</p><div className="note warning"><b>2 provenance issues block approval</b><br />Scholarships has no source URL. Entry Requirements cites a URL not among fetched pages.</div>{programmes.map((programme) => <article className="card" key={programme.degreeProgram} style={{ marginTop: 12, border: 0, background: "var(--card)" }}><div className="cardhead"><span><h2>{programme.degreeProgram}</h2><small className="muted">{programme.studyLevel} · {programme.subject}</small></span><span><StatusBadge>{programme.researchStatus === "Researched – needs recheck" ? "Needs recheck" : programme.researchStatus}</StatusBadge> <ActionButton>Approve all</ActionButton></span></div>{([ ["Application Deadline", programme.deadline], ["Tuition Fee (International)", programme.tuitionInternational], ["Entry Requirements", programme.entryRequirements], ["Scholarships", programme.scholarships], ["Study Subjects", programme.studySubjects]] as const).map(([name, value]) => <button key={name} className={`reviewuni fieldrow ${field === name ? "selected" : ""}`} onClick={() => setField(name)}><b>{name}</b><span>{value.value}<small className="muted" style={{ display: "block" }}>{value.sourceUrl.replace("https://", "")}</small></span><span><StatusBadge>{value.state}</StatusBadge><small className="muted" style={{ display: "block" }}>✓ {value.lastVerified}</small></span></button>)}</article>)}</section>
      <aside className="sourcepane"><div className="navhead" style={{ margin: 0 }}>Source · {field}</div><p className="note mono">https://study.uq.edu.au/study-options/programs/bachelor-engineering-honours-2342#fees</p><h3>Extracted snippet</h3><p className="card">International students. <b>Indicative annual fee 2027: AUD $58,384.</b> Fees are charged per unit and the annual amount assumes a standard full-time study load.</p><div className="sourcecapture">stored page capture</div><b>Other pages mentioning fees (2)</b></aside>
    </div> : <Changes />}</StateGate>
  </AppShell>;
}

function Changes() {
  const rows = [["Tuition Fee (International)", "SEK 310,000 total (2 years)", "SEK 335,000 total (2 years)"], ["Application Deadline", "16 Oct 2025 – 15 Jan 2026", "15 Oct 2026 – 15 Jan 2027"], ["Entry Requirements", "Bachelor ≥ 180 ECTS incl. 30 ECTS programming", "Bachelor ≥ 180 ECTS incl. 30 ECTS CS and 20 ECTS maths"], ["Scholarships", "KTH Scholarship — full tuition, 2 years", "Not found — previous page returns 404"]];
  return <div style={{ maxWidth: 800, margin: "0 auto" }}><h2>KTH Royal Institute of Technology</h2><p className="muted">QS #12 · Sweden · Master’s taught in English</p>{rows.map((row, index) => <article className="card" key={row[0]} style={{ marginBottom: 10, border: index === 0 ? "1.5px solid var(--ink)" : undefined }}><div className="cardhead"><h2>{row[0]}</h2><StatusBadge>Changed</StatusBadge></div><div className="diff"><div className="diffbox"><small>OLD</small><b style={{ display: "block" }}>{row[1]}</b><u>kth.se/… · fetched 14 Sep 2025</u></div><span>→</span><div className="diffbox new"><small>NEW</small><b style={{ display: "block" }}>{row[2]}</b><u>kth.se/… · fetched 08 Oct 2026</u></div></div><div style={{ marginTop: 9 }}><ActionButton>Approve new</ActionButton> <ActionButton className="btn secondary">Keep old value</ActionButton> <ActionButton className="btn secondary">Edit value</ActionButton></div></article>)}</div>;
}
