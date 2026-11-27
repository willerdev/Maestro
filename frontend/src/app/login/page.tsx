"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { apiJson, saveSession } from "@/lib/api";
import { homeFor } from "@/components/Shell";
import { AuthCard } from "@/components/AuthCard";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [registerOpen, setRegisterOpen] = useState(false);

  useEffect(() => {
    apiJson<{ open: boolean }>("/api/v1/auth/register-open")
      .then((body) => setRegisterOpen(Boolean(body.open)))
      .catch(() => setRegisterOpen(false));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      if (mfaToken) {
        const body = await apiJson<{ access_token: string; refresh_token?: string }>("/api/v1/auth/mfa", {
          method: "POST",
          body: JSON.stringify({ mfa_token: mfaToken, code: form.get("code") }),
        });
        saveSession(body.access_token, body.refresh_token);
        router.push("/dashboard");
        return;
      }
      const body = await apiJson<{ access_token?: string; refresh_token?: string; mfa_required?: boolean; mfa_token?: string; user?: { roles: string[] } }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      if (body.mfa_required && body.mfa_token) {
        setMfaToken(body.mfa_token);
        return;
      }
      if (body.access_token) saveSession(body.access_token, body.refresh_token);
      router.push(homeFor(body.user?.roles || []));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <AuthCard title="Sign in" error={error}>
      <form className="flex flex-col gap-3" onSubmit={onSubmit}>
        {mfaToken ? (
          <>
            <p className="text-sm text-muted">Password accepted. Enter the Google Authenticator code.</p>
            <input name="code" inputMode="numeric" autoComplete="one-time-code" placeholder="Google Authenticator code" required />
          </>
        ) : (
          <>
            <input name="email" type="email" placeholder="Email" required />
            <input name="password" type="password" placeholder="Password" required />
          </>
        )}
        <button className="primary" type="submit">{mfaToken ? "Confirm code" : "Enter desk"}</button>
      </form>
      <div className="text-sm text-muted mt-4 flex flex-wrap gap-3 justify-between">
        {registerOpen ? <Link href="/register">Create a firm</Link> : null}
        <Link href="/join">Apply to join</Link>
        <Link href="/forgot-password">Reset password</Link>
        <Link href="/account-recovery">Lost the account</Link>
      </div>
    </AuthCard>
  );
}
