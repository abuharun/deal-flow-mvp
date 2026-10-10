"use client";
import { createContext, useCallback, useContext, useState } from "react";
const ToastContext=createContext<()=>void>(()=>{});
export function ToastProvider({children}:{children:React.ReactNode}){const [shown,setShown]=useState(false);const show=useCallback(()=>{setShown(true);window.setTimeout(()=>setShown(false),2200)},[]);return <ToastContext.Provider value={show}>{children}<div className={`toast ${shown?"show":""}`} role="status" aria-live="polite">Not connected yet</div></ToastContext.Provider>}
export const useToast=()=>useContext(ToastContext);
export function ActionButton({children,className="btn primary",disabled=false}:{children:React.ReactNode;className?:string;disabled?:boolean}){const toast=useToast();return <button type="button" className={className} disabled={disabled} onClick={toast}>{children}</button>}
