"use client";

import { use } from "react";
import { Report } from "@/components/Report";

export default function Check({ params }: PageProps<"/check/[id]">) {
  const { id } = use(params);
  return <Report id={decodeURIComponent(id)} />;
}
