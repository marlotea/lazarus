/** Numbered section heading: a dark circle with the number, then a 17px semibold title. */
export function SectionHeading({
  n,
  id,
  children,
  action,
}: {
  n: number;
  id?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 id={id} className="flex items-center gap-2.5 text-[17px] font-semibold">
        <span
          className="flex size-6 items-center justify-center rounded-full bg-zinc-950 font-mono text-xs text-white"
          aria-hidden
        >
          {n}
        </span>
        {children}
      </h2>
      {action}
    </div>
  );
}
