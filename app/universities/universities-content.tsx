"use client";
import {useSearchParams} from "next/navigation";import {StateGate} from "@/components/StateGate";import {UniversitiesTable} from "./universities-table";
export function UniversitiesContent(){const state=useSearchParams()?.get("state")??undefined;return <StateGate state={state} kind="universities"><UniversitiesTable/></StateGate>}
