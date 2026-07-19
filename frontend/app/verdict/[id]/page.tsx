// Shareable verdict permalink: /verdict/<uuid>.
//
// A server component — the verdict is fetched during render with the
// server-side API key (lib/api), so this page works with JS disabled, is
// crawlable, and never exposes the backend or its key to the browser.

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getVerdict } from "@/lib/api";

export const dynamic = "force-dynamic";

const VERDICT_STYLES: Record<string, { label: string; className: string }> = {
  true: { label: "TRUE", className: "verdict-true" },
  false: { label: "FALSE", className: "verdict-false" },
  mixed: { label: "MIXED", className: "verdict-mixed" },
  unverifiable: { label: "UNVERIFIABLE", className: "verdict-unverifiable" },
};

interface Props {
  params: { id: string };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const result = await getVerdict(params.id).catch(() => null);
  if (!result) return { title: "Verdict not found — TruthLayer" };
  const style = VERDICT_STYLES[result.verdict];
  return {
    title: `${style?.label ?? result.verdict}: ${result.claim} — TruthLayer`,
    description: result.rationale,
  };
}

export default async function VerdictPage({ params }: Props) {
  const result = await getVerdict(params.id).catch(() => null);
  if (!result) notFound();

  const style = VERDICT_STYLES[result.verdict] ?? {
    label: result.verdict.toUpperCase(),
    className: "verdict-unverifiable",
  };
  const assessed =
    result.source_assessments && result.source_assessments.length > 0
      ? result.source_assessments
      : result.sources.map((url) => ({ url, stance: undefined as undefined }));

  return (
    <main className="container">
      <h1>
        <Link href="/" className="home-link">
          TruthLayer
        </Link>
      </h1>
      <p className="tagline">A shared fact-check verdict. Check your own claim on the homepage.</p>

      <div className="card result">
        <p className="permalink-claim">&ldquo;{result.claim}&rdquo;</p>
        <div className="verdict-row">
          <span className={`verdict-badge ${style.className}`}>{style.label}</span>
          <span className="confidence">
            {Math.round(result.confidence * 100)}% confidence
            {result.low_confidence && (
              <em className="low-conf"> — low confidence; evidence may be incomplete</em>
            )}
          </span>
        </div>

        <p className="rationale">{result.rationale}</p>

        {assessed.length > 0 ? (
          <div className="sources">
            <h2>Sources</h2>
            <ul>
              {assessed.map((a) => (
                <li key={a.url}>
                  {a.stance && (
                    <span className={`stance-badge stance-${a.stance}`}>{a.stance}</span>
                  )}
                  <a href={a.url} target="_blank" rel="noopener noreferrer nofollow">
                    {a.url}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="no-sources">No sources were cited for this verdict.</p>
        )}
      </div>

      <p className="disclaimer">
        TruthLayer verdicts are produced by an automated AI pipeline and{" "}
        <strong>may be wrong</strong> — always check the cited sources yourself.
      </p>
    </main>
  );
}
