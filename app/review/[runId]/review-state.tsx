"use client";
import {useSearchParams} from "next/navigation";import {ReviewClient} from "./review-client";
export function ReviewState({runId}:{runId:string}){const state=useSearchParams()?.get("state")??undefined;return <ReviewClient runId={runId} state={state}/>}
