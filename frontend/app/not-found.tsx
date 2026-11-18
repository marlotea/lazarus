import Link from "next/link";

/** Unknown URLs (and `notFound()`), inside the app shell. */
export default function NotFound() {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-5 py-14 text-center">
      <h1 className="text-[17px] font-semibold">Page not found</h1>
      <p className="mt-1 text-zinc-500">There is nothing at this address.</p>
      <Link href="/experiments" className="mt-3 inline-block text-zinc-500 underline">
        Back to experiments
      </Link>
    </div>
  );
}
