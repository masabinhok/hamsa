import type { Metadata } from "next";
import { Cover } from "./Book";

export const metadata: Metadata = {
  title: "The Hamsa Book",
  description:
    "Why Hamsa exists, how it checks a disaster post in about a minute, why a person always decides, and how well it has done on real posts.",
};

export default function About() {
  return <Cover />;
}
