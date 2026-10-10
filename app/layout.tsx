import type {Metadata} from "next";import {Inter} from "next/font/google";import "./globals.css";import {ToastProvider} from "@/components/Toast";
const inter=Inter({subsets:["latin"],display:"swap"});
export const metadata:Metadata={title:"Bvosita",description:"University programme research operations"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body className={inter.className}><ToastProvider>{children}</ToastProvider></body></html>}
