import Image from "next/image";
import swan from "@/app/icon.svg";

// The swan mark beside the wordmark; decorative, since the name is always written next to it.
export function Mark({ size = 28 }: { size?: number }) {
  return <Image src={swan} alt="" width={size} height={size} priority />;
}
