"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { armWork, pendingWork, subscribeBusy } from "@/lib/busy";

function quiet(button: HTMLButtonElement) {
  return Boolean(button.closest(".theme-toggle, .desk-menu, .desk-rail, .desk-icons, .desk-more, .wallet-switch, .chart-toolbar, .desk-toolbar, .mode-switch"));
}

function watch(button: HTMLButtonElement) {
  if (button.dataset.busy === "1" || button.disabled || quiet(button)) return;
  button.dataset.busy = "1";
  button.classList.add("is-busy");
  button.setAttribute("aria-busy", "true");
  const release = armWork();
  const base = pendingWork();
  const started = performance.now();
  let sawWork = false;
  let timer = 0;
  const finish = () => {
    window.clearTimeout(timer);
    release();
    button.classList.remove("is-busy");
    button.removeAttribute("aria-busy");
    delete button.dataset.busy;
  };
  const tick = () => {
    if (pendingWork() > base) sawWork = true;
    if (sawWork && pendingWork() <= base) {
      finish();
      return;
    }
    if (!sawWork && performance.now() - started > 450) {
      finish();
      return;
    }
    timer = window.setTimeout(tick, 40);
  };
  tick();
}

export function BusyRoot() {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const [navigating, setNavigating] = useState(false);

  useEffect(() => subscribeBusy(setActive), []);

  useEffect(() => {
    setNavigating(true);
    const timer = window.setTimeout(() => setNavigating(false), 450);
    return () => window.clearTimeout(timer);
  }, [pathname]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest("button");
      if (button instanceof HTMLButtonElement) watch(button);
    }
    function onSubmit(event: Event) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const submitter = (event as SubmitEvent).submitter;
      const button = submitter instanceof HTMLButtonElement
        ? submitter
        : form.querySelector("button[type='submit'], button:not([type])");
      if (button instanceof HTMLButtonElement) watch(button);
    }
    document.addEventListener("click", onClick, true);
    document.addEventListener("submit", onSubmit, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("submit", onSubmit, true);
    };
  }, []);

  const on = active || navigating;
  return (
    <div className={on ? "loading-bar on" : "loading-bar"} role="progressbar" aria-hidden={on ? undefined : true} aria-valuetext={on ? "Loading" : undefined}>
      <i />
    </div>
  );
}
