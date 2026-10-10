"use client";

import { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      triggerRef.current = document.activeElement as HTMLElement;
      dialog.showModal();
      requestAnimationFrame(() => dialog.querySelector<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")?.focus());
    } else if (!open && dialog.open) dialog.close();
  }, [open]);

  const close = () => {
    onClose();
    requestAnimationFrame(() => triggerRef.current?.focus());
  };

  return <dialog ref={dialogRef} className="drawer" aria-labelledby={titleId} onCancel={(event) => { event.preventDefault(); close(); }} onClick={(event) => { if (event.target === event.currentTarget) close(); }}><div className="drawer-surface"><div className="modalhead"><h2 id={titleId}>{title}</h2><button className="iconbtn" type="button" onClick={close} aria-label="Close drawer"><X size={18} aria-hidden="true" /></button></div>{children}</div></dialog>;
}
