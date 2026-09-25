import { useState } from "react";

export const MARK = (
  <svg width="22" height="22" viewBox="0 0 512 512" aria-hidden="true">
    <defs>
      <linearGradient id="pipe-copper" gradientUnits="userSpaceOnUse" x1="100" y1="80" x2="400" y2="440">
        <stop offset="0" stopColor="#FFD694" />
        <stop offset="0.4" stopColor="#FFC46B" />
        <stop offset="1" stopColor="#E8802A" />
      </linearGradient>
    </defs>
    <path d="M157 148 L285 256 L157 364" fill="none" stroke="url(#pipe-copper)" strokeWidth="58" strokeLinecap="round" strokeLinejoin="round" />
    <rect x="329" y="188" width="56" height="176" rx="16" fill="url(#pipe-copper)" />
    <circle cx="157" cy="148" r="15" fill="#160B03" />
    <circle cx="157" cy="364" r="15" fill="#160B03" />
  </svg>
);

const TOKEN_CA = (import.meta.env.VITE_TOKEN_CA || "").trim();

function ProjectCA() {
  const [copied, setCopied] = useState(false);
  const value = TOKEN_CA || "TBA";
  const label = TOKEN_CA ? `${TOKEN_CA.slice(0, 4)}...${TOKEN_CA.slice(-4)}` : value;

  if (!TOKEN_CA) {
    return <span className="project-ca" title="The token contract address will appear here">CA: {label}</span>;
  }

  return (
    <button
      className="project-ca project-ca-copy"
      title="Copy token contract address"
      onClick={() => {
        navigator.clipboard?.writeText(TOKEN_CA).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      }}
    >
      CA: {copied ? "copied" : label}
    </button>
  );
}

export default function Header({ children, end }) {
  return (
    <header className="top">
      <a className="brand" href="/" aria-label="PIPE terminal home">{MARK}<b>PIPE</b></a>
      {children}
      <a className="top-link" href="/docs">docs</a>
      <ProjectCA />
      <a
        className="x-link"
        href="https://x.com/pipeterminal"
        target="_blank"
        rel="noreferrer"
        aria-label="Open PIPE on X"
        title="@pipeterminal"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M18.9 2H22l-6.77 7.74L23.2 22H17l-4.86-6.35L6.58 22H3.47l7.22-8.25L3.05 2H9.4l4.39 5.8L18.9 2Zm-1.09 17.84h1.72L8.46 4.05H6.62l11.19 15.79Z" />
        </svg>
      </a>
      {end}
    </header>
  );
}
