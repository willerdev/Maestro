export function accountHome(method: string, id: string) {
  if (method === "blockchain") return "/contracts";
  if (method === "mining") return "/project-coin";
  if (method === "passprop") return `/pass-props/${id}`;
  return `/accounts/${id}`;
}
