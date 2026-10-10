"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { PageHeader } from "@/components/PageHeader";
import { DataTable } from "@/components/DataTable";
import { Drawer } from "@/components/Drawer";
import { StateGate } from "@/components/StateGate";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, useToast } from "@/components/Toast";
import { getSchedules } from "@/lib/data";

export function SchedulesClient() {
  const state = useSearchParams()?.get("state") ?? undefined;
  const data = getSchedules();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(data[0].id);
  const toast = useToast();
  const [subjects, setSubjects] = useState(["Mech. Eng.", "Comp. Sci."]);
  const edit = data.find((schedule) => schedule.id === selected) ?? data[0];
  const openSchedule = (id: string) => { setSelected(id); setOpen(true); };

  return (
    <AppShell>
      <PageHeader title="Schedules" eyebrow="4 schedules · 3 enabled · times in Asia/Tashkent" actions={<button className="btn primary" onClick={() => setOpen(true)}>New schedule</button>} />
      <StateGate state={state} kind="schedules">
        <section className="card" style={{ padding: 0 }}>
          <DataTable label="Schedules" headers={["Name", "Scope", "Subjects", "Frequency", "Next run", "Last run", "Outcome", "On"]}>
            {data.map((schedule) => (
              <tr key={schedule.id}>
                <td><button className="table-action" onClick={() => openSchedule(schedule.id)}>{schedule.name}</button></td>
                <td>{schedule.scope}</td>
                <td>{schedule.subjects.map((subject) => subject.split(" ").map((word) => word[0]).join("")).join(" · ")}</td>
                <td>{schedule.frequency}</td><td><b>{schedule.nextRun}</b></td><td>{schedule.lastRun}</td>
                <td><StatusBadge>{schedule.lastStatus}</StatusBadge></td>
                <td><button className={`toggle ${schedule.enabled ? "on" : ""}`} aria-label={`${schedule.enabled ? "Disable" : "Enable"} ${schedule.name}`} aria-pressed={schedule.enabled} onClick={toast}><i /></button></td>
              </tr>
            ))}
          </DataTable>
        </section>
        <p className="muted small">A scheduled run behaves like a manual run; results land in Review in “Changes since last run” mode.</p>
      </StateGate>
      <Drawer open={open} onClose={() => setOpen(false)} title={open && selected === data[0].id ? "Edit schedule" : "Edit schedule"}>
        <div className="stack">
          <label className="field"><span>Name</span><input className="input" defaultValue={edit.name} key={`${edit.id}-name`} /></label>
          <label className="field"><span>Scope (saved filter)</span><select className="input" defaultValue="all"><option value="all">All universities</option></select></label>
          <fieldset><legend>Subjects</legend><div className="pillrow">{["Mech. Eng.", "Comp. Sci.", "Civil Eng."].map((subject) => <button type="button" aria-pressed={subjects.includes(subject)} className={`filter ${subjects.includes(subject) ? "active" : ""}`} onClick={() => setSubjects((current) => current.includes(subject) ? current.filter((item) => item !== subject) : [...current, subject])} key={subject}>{subject}</button>)}</div></fieldset>
          <fieldset><legend>Frequency</legend><label className="choice"><input type="radio" name="freq" /> Yearly on a date</label><label className="choice"><input type="radio" name="freq" defaultChecked /> Every <input aria-label="Frequency in months" className="input compact-input" defaultValue="18" /> months</label></fieldset>
          <fieldset><legend>Fields to refresh</legend>{["Application Deadline", "Tuition Fee (International)", "Entry Requirements", "Scholarships", "Study Subjects"].map((field, index) => <label className="choice" key={field}><input type="checkbox" defaultChecked={index !== 3} />{field}</label>)}</fieldset>
          <p className="note"><b>Next run 15 Jan 2027, 02:00</b> · 486 records, 1,640 jobs · ≈ USD 190</p>
          <div className="grid2"><ActionButton>Save</ActionButton><ActionButton className="btn secondary">Run now</ActionButton></div>
        </div>
      </Drawer>
    </AppShell>
  );
}
