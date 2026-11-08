"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RatesRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/project-coin/rates");
  }, [router]);
  return <p className="text-muted">Opening rates…</p>;
}
