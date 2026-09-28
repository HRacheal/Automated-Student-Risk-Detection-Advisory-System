"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUserJson, getToken, homeFor, parseUser } from "@/lib/api";
import { Loading } from "@/components/ui";

// "/" sends signed-in advisors to the dashboard and everyone else to the login page.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? homeFor(parseUser(getStoredUserJson())?.role) : "/login");
  }, [router]);
  return <Loading label="Opening My Coach…" />;
}
