"use client";

import { use } from "react";
import { CaseView } from "@/components/CaseView";

export default function CasePage({ params }: PageProps<"/desk/[id]">) {
  const { id } = use(params);
  return <CaseView key={id} id={id} />;
}
