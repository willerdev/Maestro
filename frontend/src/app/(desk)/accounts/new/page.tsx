"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AccountSections, accountBody, type ConnectionMethod, type Probe } from "@/components/AccountSections";
import { PageTitle } from "@/components/Shell";
import { apiJson } from "@/lib/api";

type Created = {
  id: string;
  webhook?: { url_path: string; api_key: string; signing_secret: string };
};

export default function NewAccountPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [method, setMethod] = useState<ConnectionMethod>("metaapi");
  const [probe, setProbe] = useState<Probe | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [counts, setCounts] = useState<Partial<Record<ConnectionMethod, number>>>({});
  const [enabled, setEnabled] = useState<Partial<Record<ConnectionMethod, boolean>> | undefined>();

  useEffect(() => {
    apiJson<{ counts: Partial<Record<ConnectionMethod, number>>; enabled: Partial<Record<ConnectionMethod, boolean>> }>("/api/v1/system")
      .then((info) => {
        setCounts(info.counts || {});
        setEnabled(info.enabled || {});
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const methodLimit = method === "local_mt5" || method === "passprop" ? 10 : 1;
  const methodFull = (counts[method] || 0) >= methodLimit;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<Created>("/api/v1/accounts", {
        method: "POST",
        body: JSON.stringify(accountBody(form, method, probe)),
      });
      if (method === "blockchain" || method === "mining") {
        sessionStorage.setItem("maestro-account-terms", method);
        router.push(method === "blockchain" ? "/contracts" : "/project-coin");
        return;
      }
      if (method === "passprop") {
        router.push(`/pass-props/${body.id}`);
        return;
      }
      setCreated(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account");
    }
  }

  return (
    <div className="max-w-3xl">
      <PageTitle title="Add account" detail="Give it an alias you will remember if you add more than one. One account of each type; MetaTrader and Pass Props allow up to 10. Number, broker, and size are read after the live check succeeds." />
      {error ? <p className="text-loss mb-3">{error}</p> : null}
      {methodFull ? <p className="mb-3">This type is full. Delete one from <Link className="text-accent" href="/accounts">Accounts</Link>, or choose another type.</p> : null}
      {created?.webhook ? (
        <div className="bg-panel border border-line rounded-lg p-4 text-sm">
          <p className="mb-2">Copy these webhook credentials now. They are not shown again.</p>
          <p className="num break-all">Path: {created.webhook.url_path}</p>
          <p className="num break-all mt-2">API key: {created.webhook.api_key}</p>
          <p className="num break-all mt-2">Signing secret: {created.webhook.signing_secret}</p>
          <button className="primary mt-4" onClick={() => router.push(`/accounts/${created.id}`)}>Open account</button>
        </div>
      ) : created ? (
        <div className="bg-panel border border-line rounded-lg p-4 text-sm">
          <p>Account saved. Broker passwords and API tokens stay encrypted.</p>
          <button className="primary mt-4" onClick={() => router.push(`/accounts/${created.id}`)}>Open account</button>
        </div>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={onSubmit}>
          <AccountSections method={method} onMethod={setMethod} allowWebhook showRevenue gateTerms counts={counts} enabled={enabled} onProbe={setProbe} />
          {error ? <p className="text-loss text-sm">{error}</p> : null}
          <button className="primary" type="submit" disabled={methodFull || (method !== "webhook" && method !== "blockchain" && method !== "mining" && !probe?.ok)}>
            {method === "blockchain" || method === "mining" ? "Agree and continue" : method === "passprop" ? "Save Pass Props account" : "Save account"}
          </button>
        </form>
      )}
    </div>
  );
}
