import {Suspense} from "react";import {getRunIds} from "@/lib/data";import {Skeleton} from "@/components/Skeleton";import {ReviewState} from "./review-state";
export function generateStaticParams(){return getRunIds().map(runId=>({runId}))}
export default async function Page({params}:{params:Promise<{runId:string}>}){const {runId}=await params;return <Suspense fallback={<Skeleton rows={6}/>}><ReviewState runId={runId}/></Suspense>}
