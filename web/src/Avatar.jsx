import { useEffect, useState } from "react";
import { avatarChain } from "./api.js";

/*
  One picture, several places it might live. Each failure steps to the next
  candidate rather than giving up, and the last candidate is the mint-derived
  mark, which cannot fail. The index resets when the coin changes so a
  recycled component never shows the previous coin's picture.
*/
export default function Avatar({ url, mint, size = 40, className = "av" }) {
  const chain = avatarChain(url, mint);
  const [step, setStep] = useState(0);

  useEffect(() => setStep(0), [url, mint]);

  return (
    <img
      className={className} width={size} height={size}
      src={chain[Math.min(step, chain.length - 1)]} alt=""
      loading="lazy" referrerPolicy="no-referrer"
      onError={() => setStep((s) => (s + 1 < chain.length ? s + 1 : s))}
    />
  );
}
