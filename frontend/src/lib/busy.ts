type Listener = (active: boolean) => void;

let work = 0;
let armed = 0;
const listeners = new Set<Listener>();

function emit() {
  const active = work > 0;
  listeners.forEach((listener) => listener(active));
}

export function pendingWork() {
  return work;
}

export function armWork() {
  armed += 1;
  return () => {
    armed = Math.max(0, armed - 1);
  };
}

export function beginRequest(method: string) {
  if (method === "GET" && armed === 0) return () => undefined;
  work += 1;
  emit();
  let closed = false;
  return () => {
    if (closed) return;
    closed = true;
    work = Math.max(0, work - 1);
    emit();
  };
}

export function subscribeBusy(listener: Listener) {
  listeners.add(listener);
  listener(work > 0);
  return () => {
    listeners.delete(listener);
  };
}
