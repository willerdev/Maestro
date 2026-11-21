"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { accountHome } from "@/lib/accounts";

export default function RulesPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(accountHome("metaapi", String(params.id || "")));
  }, [params.id, router]);
  return null;
}
