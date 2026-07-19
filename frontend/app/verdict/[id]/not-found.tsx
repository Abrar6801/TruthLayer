import Link from "next/link";

export default function VerdictNotFound() {
  return (
    <main className="container">
      <h1>TruthLayer</h1>
      <div className="card error" role="alert">
        <strong>Verdict not found.</strong>
        <p>
          This link may be malformed, or the verdict may have been pruned.{" "}
          <Link href="/">Check a claim yourself instead.</Link>
        </p>
      </div>
    </main>
  );
}
