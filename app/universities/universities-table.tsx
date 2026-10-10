"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { FilterBar } from "@/components/FilterBar";
import { DataTable } from "@/components/DataTable";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton } from "@/components/Toast";
import { getUniversities, getUniversityIds } from "@/lib/data";

type FilterKey = "country" | "region" | "rank" | "subject" | "level" | "status";

export function UniversitiesTable() {
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(new Set(["eth-zurich", "delft", "tsinghua"]));
  const [filters, setFilters] = useState<Record<FilterKey, boolean>>({ country: false, region: false, rank: true, subject: true, level: false, status: false });
  const ids = getUniversityIds();
  const data = useMemo(() => getUniversities().filter((university) => {
    const id = ids[university.index - 1];
    const pending = ["delft", "polimi"].includes(id);
    const matchesSearch = `${university.name} ${university.country} ${university.website}`.toLowerCase().includes(q.toLowerCase());
    return matchesSearch
      && (!filters.country || ["United Kingdom", "Switzerland", "Netherlands", "Sweden", "Italy", "Germany"].includes(university.country))
      && (!filters.region || university.region === "Asia")
      && (!filters.rank || university.qsRank <= 10)
      && (!filters.subject || (university.subjects.includes("Mechanical Engineering") && university.subjects.includes("Computer Science")))
      && (!filters.level || university.subjects.length === 3)
      && (!filters.status || pending);
  }), [filters, ids, q]);

  const toggleSelection = (id: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleFilter = (key: FilterKey) => setFilters((current) => ({ ...current, [key]: !current[key] }));
  const filterButton = (key: FilterKey, inactive: string, active: string) => <button type="button" aria-pressed={filters[key]} className={`filter ${filters[key] ? "active" : ""}`} onClick={() => toggleFilter(key)}>{filters[key] ? `${active} ×` : inactive}</button>;

  return <>
    <FilterBar search={q} onSearch={setQ}>
      {filterButton("country", "Country: Any⌄", "Country: Europe")}
      {filterButton("region", "Region: Any⌄", "Region: Asia")}
      {filterButton("rank", "QS rank: Any⌄", "QS rank 1–10")}
      {filterButton("subject", "Subject: Any⌄", "Subject: Mech. Eng. + Comp. Sci.")}
      {filterButton("level", "Level: Any⌄", "Level: Bachelor + Master")}
      {filterButton("status", "Status: Any⌄", "Status: Pending")}
    </FilterBar>
    {selected.size > 0 && <div className="selectionbar"><b>{selected.size} selected <span className="selection-detail">· {selected.size * 5 + 1} programmes · 2 stale</span></b><span className="headeractions"><ActionButton>Add to schedule</ActionButton><ActionButton>Start run</ActionButton></span></div>}
    <section className="card" style={{ padding: "5px 0 0" }}><DataTable label="Universities" headers={["", "#", "QS", "University", "Country", "Region", "Subjects", "Progs", "Status", "Verified", "Fresh"]}>{data.map((university, index) => {
      const id = ids[university.index - 1];
      const stale = ["eth-zurich", "tsinghua"].includes(id);
      const pending = ["delft", "polimi"].includes(id);
      return <tr key={id}><td><input aria-label={`Select ${university.name}`} type="checkbox" checked={selected.has(id)} onChange={() => toggleSelection(id)} /></td><td>{university.index}</td><td>{university.qsRank}</td><td><Link className="tablelink" href={`/universities/${id}`}>{university.name}</Link></td><td>{university.country}</td><td>{university.region}</td><td><span className="pillrow">{university.subjects.map((subject) => <span className="subjectpill" key={subject}>{subject.split(" ").map((word) => word[0]).join("")}</span>)}</span></td><td>{university.subjects.length * 2}</td><td><StatusBadge>{pending ? "Pending" : stale ? "Needs recheck" : "Researched"}</StatusBadge></td><td>{pending ? "Never" : stale ? "18 Aug 2025" : index > 7 ? "08 Oct 2026" : "12 Mar 2026"}</td><td>{stale ? <StatusBadge>Stale</StatusBadge> : pending ? "—" : <StatusBadge>Fresh</StatusBadge>}</td></tr>;
    })}</DataTable></section>
  </>;
}
