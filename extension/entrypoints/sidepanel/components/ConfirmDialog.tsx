import { useEffect, useRef } from "react";
import type { Candidate } from "../../../shared/types";

interface Props {
  candidate: Candidate;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  candidate,
  onConfirm,
  onCancel,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();

    return () => {
      dialog?.close();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      aria-labelledby="confirm-title"
      className="fixed inset-0 m-auto w-[90%] max-w-sm rounded-2xl border border-zinc-200 bg-white p-5 shadow-xl backdrop:bg-black/40"
    >
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-red-50 font-bold text-[#C5050C]">
        !
      </div>

      <h2 id="confirm-title" className="text-lg font-bold">
        Confirm your selection
      </h2>

      <p className="mt-2 text-sm text-zinc-500">
        You have selected the following option:
      </p>

      <div className="my-4 rounded-lg bg-zinc-100 p-3 text-sm font-semibold">
        {candidate.label}
      </div>

      <p className="text-xs leading-relaxed text-zinc-500">
        This is a demonstration. Confirming will simulate a booking,
        but will not make a real reservation.
      </p>

      <div className="mt-5 flex gap-2">
        <button
          autoFocus
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium hover:bg-zinc-100"
        >
          Go back
        </button>

        <button
          type="button"
          onClick={onConfirm}
          className="flex-1 rounded-lg bg-[#C5050C] px-3 py-2 text-sm font-semibold text-white hover:bg-red-800"
        >
          Confirm
        </button>
      </div>
    </dialog>
  );
}
