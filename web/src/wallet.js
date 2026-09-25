/*
  The wallet.

  This file is deliberately small, and the reason is the whole trust model of
  the terminal: the only thing that ever signs is the reader's own wallet, in
  their own browser, after their own confirmation. Nothing here holds a key,
  no key is ever sent anywhere, and the backend builds an unsigned transaction
  it has no way to submit.

  Phantom, Solflare and Backpack all inject a provider with the same three
  methods, so one path covers them rather than three. `isPhantom`-style flags
  only decide what the button is allowed to call itself.
*/

export const WALLETS = [
  { id: "phantom", label: "Phantom", site: "https://phantom.app/", pick: (w) => w.phantom?.solana || (w.solana?.isPhantom ? w.solana : null) },
  { id: "solflare", label: "Solflare", site: "https://solflare.com/", pick: (w) => (w.solflare?.isSolflare ? w.solflare : null) },
  { id: "backpack", label: "Backpack", site: "https://backpack.app/", pick: (w) => (w.backpack?.isBackpack ? w.backpack : null) },
];

export function installed() {
  if (typeof window === "undefined") return [];
  return WALLETS.filter((w) => !!w.pick(window));
}

export function provider(id) {
  const entry = WALLETS.find((w) => w.id === id);
  const found = entry && typeof window !== "undefined" ? entry.pick(window) : null;
  if (!found) throw new Error(`${entry ? entry.label : "That wallet"} is not installed in this browser.`);
  return found;
}

export async function connect(id) {
  const p = provider(id);
  const res = await p.connect();
  const key = (res?.publicKey || p.publicKey)?.toString();
  if (!key) throw new Error("The wallet connected but returned no address.");
  return { id, address: key, provider: p };
}

export async function disconnect(id) {
  try {
    await provider(id).disconnect();
  } catch {
    /* a wallet that is already gone is disconnected enough */
  }
}

/*
  Jupiter returns a base64 versioned transaction. It is decoded here and handed
  to the wallet as an object, because that is the form every one of these
  wallets accepts for a v0 transaction — passing the raw bytes works on some
  and silently fails on others.
*/
export async function signAndSend(id, base64Transaction) {
  const { VersionedTransaction } = await import("@solana/web3.js");
  const bytes = Uint8Array.from(atob(base64Transaction), (c) => c.charCodeAt(0));
  const tx = VersionedTransaction.deserialize(bytes);
  const p = provider(id);
  const out = await p.signAndSendTransaction(tx);
  const signature = typeof out === "string" ? out : out?.signature;
  if (!signature) throw new Error("The wallet signed but returned no signature.");
  return signature;
}

/*
  Wallets word a rejection a dozen ways and none of them is an error the
  reader caused. It comes back as one plain sentence so the panel never shows
  a stack trace where a "you cancelled" belongs.
*/
export function readableError(err) {
  const message = String(err?.message || err || "Something went wrong.");
  if (/user rejected|declined|cancell?ed|denied/i.test(message)) return "You cancelled the transaction in your wallet.";
  if (/insufficient/i.test(message)) return "Not enough SOL in the wallet for this trade and its fees.";
  if (/blockhash|expired/i.test(message)) return "The quote expired before it was signed. Take a fresh one.";
  return message;
}
