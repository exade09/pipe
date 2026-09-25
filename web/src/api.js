/*
  Every route answers the same envelope: { ok, data, error }. Unwrapping it in
  one place means no component has to check `ok`, and a failure arrives as a
  thrown Error carrying the server's own message — which matters here, because
  one of those messages ("holders need a keyed RPC") is a real answer the user
  is meant to read rather than a bug.
*/

async function get(path, signal) {
  const response = await fetch(path, { signal, cache: "no-store" });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`${path} returned ${response.status} and no JSON`);
  }
  if (!payload.ok) throw new Error(payload.error || `${path} failed`);
  return payload.data;
}

export const fetchHealth = (signal) => get("/api/health", signal);
export const fetchFeed = ({ limit = 40 } = {}, signal) => get(`/api/feed?limit=${limit}`, signal);
export const fetchToken = (mint, signal) => get(`/api/token/${mint}`, signal);
export const fetchHolders = (mint, signal) => get(`/api/token/${mint}/holders`, signal);

/* ------------------------------------------------------------ formatting */

export function usd(value) {
  const n = Number(value) || 0;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}b`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}m`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}k`;
  if (n > 0 && n < 1) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(0)}`;
}

export function age(minutes) {
  const m = Number(minutes) || 0;
  if (m < 60) return `${m}m`;
  if (m < 1440) return `${Math.floor(m / 60)}h`;
  return `${Math.floor(m / 1440)}d`;
}

/* Solana addresses are long. Both ends carry meaning, the middle does not. */
export const short = (a) => (a ? `${a.slice(0, 4)}…${a.slice(-4)}` : "—");

/*
  Image hosts, in the order worth trying.

  pump.fun writes its metadata to IPFS and hands out ipfs.io links, and
  ipfs.io answers 403 to us — so the CID is re-pointed at pump's own pinata
  gateway on the way out of the backend. That gateway serves most of them and
  403s a minority for reasons it does not explain; the public pinata gateway
  serves exactly those. So an IPFS picture gets two chances before the mark
  stands in, and a picture hosted anywhere else gets one.
*/
const GATEWAYS = [
  "https://pump.mypinata.cloud/ipfs/",
  "https://gateway.pinata.cloud/ipfs/",
];

export function avatarChain(url = "", mint = "") {
  const out = [];
  if (url) {
    out.push(url);
    const cut = url.indexOf("/ipfs/");
    if (cut > -1) {
      const cid = url.slice(cut + 6);
      GATEWAYS.forEach((g) => {
        if (!out.includes(g + cid)) out.push(g + cid);
      });
    }
  }
  out.push(fallbackAvatar(mint));
  return out;
}

/*
  A coin's real image comes from its metadata and reaches us through pump.fun
  or DexScreener. For the first moments there isn't one, and a grey box in
  every row makes the whole feed look broken — so a mint-derived mark stands
  in. Same mint, same picture, every time.
*/
export function fallbackAvatar(mint = "") {
  let h = 2166136261;
  for (let i = 0; i < mint.length; i++) {
    h ^= mint.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const hue = Math.abs(h) % 360;
  const hue2 = (hue + 55 + (Math.abs(h >> 7) % 140)) % 360;
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
    `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="hsl(${hue},64%,54%)"/>` +
    `<stop offset="1" stop-color="hsl(${hue2},58%,34%)"/></linearGradient></defs>` +
    `<rect width="32" height="32" fill="url(#g)"/>` +
    `<circle cx="16" cy="16" r="10" fill="none" stroke="rgba(0,0,0,.42)" stroke-width="3.4"/>` +
    `<circle cx="16" cy="16" r="4" fill="rgba(255,255,255,.7)"/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
