"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiJson, saveSession } from "@/lib/api";
import { AuthCard } from "@/components/AuthCard";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [open, setOpen] = useState<boolean | null>(null);

  useEffect(() => {
    apiJson<{ open: boolean }>("/api/v1/auth/register-open")
      .then((body) => setOpen(Boolean(body.open)))
      .catch(() => setOpen(false));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<{ access_token: string; refresh_token?: string }>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
          full_name: form.get("full_name"),
          organization_name: form.get("organization_name"),
        }),
      });
      saveSession(body.access_token, body.refresh_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  }

  if (open === false) {
    return (
      <AuthCard title="Signup closed" error={error}>
        <p className="text-sm text-muted">This desk already has an owner. New people apply to join; they cannot create another owner login.</p>
        <div className="text-sm text-muted mt-4 flex flex-wrap gap-3">
          <Link href="/login">Sign in</Link>
          <Link href="/join">Apply to join</Link>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Create a firm" error={error}>
      {open === null ? <p className="text-sm text-muted">Checking whether signup is still open.</p> : null}
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        <input name="organization_name" placeholder="Organization" required />
        <input name="full_name" placeholder="Your name" required />
        <input name="email" type="email" placeholder="Email" required />
        <input name="password" type="password" placeholder="Password, 12+ chars" required />
        <button className="primary" type="submit">Create firm</button>
      </form>
      <Link className="text-sm text-muted mt-4 inline-block" href="/login">Already registered</Link>
    </AuthCard>
  );
}
