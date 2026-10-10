import {Suspense} from "react";import {Skeleton} from "@/components/Skeleton";import {SchedulesClient} from "./schedules-client";
export default function Page(){return <Suspense fallback={<Skeleton rows={6}/>}><SchedulesClient/></Suspense>}
