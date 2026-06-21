"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** Read/write filter+view state in the URL query string so views are shareable and
 * survive reload. Pass null (or "") to drop a param, keeping URLs clean at defaults. */
export function useUrlState() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const get = (key: string, fallback = "") => sp.get(key) ?? fallback;

  const set = (updates: Record<string, string | null>) => {
    const p = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === null || v === "") p.delete(k);
      else p.set(k, v);
    }
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  return { get, set };
}
