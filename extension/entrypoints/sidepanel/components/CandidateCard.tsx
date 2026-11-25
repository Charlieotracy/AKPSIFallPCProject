import type { Candidate } from "../../../shared/types";

interface Props {
  candidate: Candidate;
  index: number;
  disabled: boolean;
  onSelect: (candidate: Candidate) => void;
}

export default function CandidateCard({
  candidate,
  index,
  disabled,
  onSelect,
}: Props) {
  const fit =
    candidate.fit === null
      ? null
      : Math.round(candidate.fit * 100);

  const bookable = candidate.data.bookable === true;

  return (
    <article className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Option {index + 1}
        </span>

        {index === 0 && fit !== null && (
          <span className="rounded-full bg-red-50 px-2 py-1 text-xs font-semibold text-[#C5050C]">
            Best match
          </span>
        )}
      </div>

      <h3 className="text-sm font-semibold text-zinc-900">
        {candidate.label}
      </h3>

      {fit !== null && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-xs text-zinc-500">
            <span>Example preference fit</span>
            <span>{fit}%</span>
          </div>

          <div className="h-1.5 overflow-hidden rounded-full bg-zinc-100">
            <div
              className="h-full rounded-full bg-[#C5050C]"
              style={{ width: `${fit}%` }}
            />
          </div>
        </div>
      )}

      {bookable ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSelect(candidate)}
          className="mt-4 w-full rounded-lg border border-[#C5050C] px-3 py-2 text-sm font-semibold text-[#C5050C] transition hover:bg-red-50 disabled:opacity-40"
        >
          Select option
        </button>
      ) : (
        <p className="mt-3 text-xs text-zinc-500">
          Example listing only. Jev does not purchase tickets.
        </p>
      )}
    </article>
  );
}
