import { useEffect, useRef, useState } from "react";
import type {
  BackendEvent,
  Candidate,
  ChatMessage,
  Page,
  TaskStatus,
} from "../../shared/types";

import CandidateCard from "./components/CandidateCard";
import ConfirmDialog from "./components/ConfirmDialog";
import { mockSearch, mockBook } from "./mockBackend";

const quickActions = [
  {
    icon: "01",
    title: "Find a course",
    description: "Explore open sections",
    prompt: "Find open sections of CS 577",
  },
  {
    icon: "02",
    title: "Book an exam",
    description: "Find CBTF exam slots",
    prompt: "Book my CS 354 exam",
  },
  {
    icon: "03",
    title: "UHS appointment",
    description: "Explore appointment options",
    prompt: "Find a UHS appointment",
  },
  {
    icon: "04",
    title: "Find tickets",
    description: "Explore Badger games",
    prompt: "Find Badgers basketball tickets",
  },
];

export default function App() {
  const [page, setPage] = useState<Page>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const operationLock = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, candidates, progress, page]);

  function addMessage(
    role: ChatMessage["role"],
    text: string
  ) {
    setMessages((previous) => [
      ...previous,
      {
        id: crypto.randomUUID(),
        role,
        text,
      },
    ]);
  }

  function handleEvent(event: BackendEvent) {
    switch (event.type) {
      case "assistant_message":
        addMessage("assistant", event.text);
        break;

      case "progress":
        setProgress(event.note);
        break;

      case "candidates":
        setCandidates(event.candidates);
        setProgress("");
        break;

      case "status":
        setStatus(event.status);
        break;

      case "done":
        addMessage("assistant", event.summary);
        setCandidates([]);
        setProgress("");
        break;
    }
  }

  async function sendMessage() {
    const text = input.trim();

    if (!text || operationLock.current || selected) return;

    operationLock.current = true;
    setBusy(true);
    setError("");
    setInput("");
    setCandidates([]);
    setProgress("");

    // Do not retain raw health-related requests in chat history.
    const healthRelated = /uhs|appointment|doctor|health/i.test(text);

    addMessage(
      "user",
      healthRelated ? "UHS scheduling request" : text
    );

    try {
      await mockSearch(text, handleEvent);
    } catch {
      setStatus("failed");
      setError("The demo search failed. Please try again.");
    } finally {
      operationLock.current = false;
      setBusy(false);
      setProgress("");
    }
  }

  function selectCandidate(candidate: Candidate) {
    if (
      operationLock.current ||
      candidate.data.bookable !== true
    ) return;

    setSelected(candidate);
    setStatus("awaiting_confirm");
  }

  function cancelSelection() {
    setSelected(null);
    setStatus("candidates");
  }

  async function confirmBooking() {
    if (!selected || operationLock.current) return;

    const candidate = selected;

    operationLock.current = true;
    setSelected(null);
    setBusy(true);
    setError("");

    try {
      await mockBook(candidate, true, handleEvent);
    } catch {
      setStatus("failed");
      setError("The simulated booking failed.");
    } finally {
      operationLock.current = false;
      setBusy(false);
      setProgress("");
    }
  }

  function resetChat() {
    if (operationLock.current || selected) return;

    setMessages([]);
    setCandidates([]);
    setInput("");
    setStatus(null);
    setProgress("");
    setError("");
  }

  return (
    <div className="flex h-dvh flex-col bg-[#fafafa] text-zinc-900">

      <header className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#C5050C] text-xl font-bold text-white">
          J
        </div>

        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">
            jev.
          </h1>
          <p className="text-xs text-zinc-500">
            UW scheduling assistant
          </p>
        </div>

        <span className="rounded-full bg-zinc-100 px-2 py-1 text-xs text-zinc-600">
          Demo
        </span>
      </header>

      <nav aria-label="Main navigation" className="flex border-b border-zinc-200 bg-white">
        {(["chat", "watches", "settings"] as Page[]).map(
          (item) => (
            <button
              key={item}
              type="button"
              aria-current={page === item ? "page" : undefined}
              onClick={() => setPage(item)}
              className={`flex-1 border-b-2 py-3 text-sm font-medium capitalize transition ${
                page === item
                  ? "border-[#C5050C] text-[#C5050C]"
                  : "border-transparent text-zinc-500 hover:text-zinc-900"
              }`}
            >
              {item}
            </button>
          )
        )}
      </nav>

      {page === "chat" ? (
        <>
          <main className="min-h-0 flex-1 overflow-y-auto p-4">

            {messages.length === 0 ? (
              <div className="py-6">
                <div className="mb-6 text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-2xl font-bold text-[#C5050C]">
                    J
                  </div>

                  <h2 className="text-2xl font-bold tracking-tight">
                    What can I schedule for you?
                  </h2>

                  <p className="mt-2 text-sm leading-relaxed text-zinc-500">
                    Less time scheduling. More time being a Badger.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {quickActions.map((action) => (
                    <button
                      key={action.title}
                      type="button"
                      onClick={() => {
                        setInput(action.prompt);
                        inputRef.current?.focus();
                      }}
                      className="rounded-xl border border-zinc-200 bg-white p-3 text-left shadow-sm transition hover:border-[#C5050C] hover:bg-red-50"
                    >
                      <span className="text-xs font-bold text-[#C5050C]">
                        {action.icon}
                      </span>

                      <h3 className="mt-2 text-sm font-semibold">
                        {action.title}
                      </h3>

                      <p className="mt-1 text-xs leading-relaxed text-zinc-500">
                        {action.description}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={resetChat}
                    className="text-xs text-zinc-500 hover:text-[#C5050C] disabled:opacity-40"
                  >
                    + New chat
                  </button>
                </div>

                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${
                      message.role === "user"
                        ? "justify-end"
                        : "justify-start"
                    }`}
                  >
                    <div
                      className={`max-w-[90%] whitespace-pre-wrap break-words rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                        message.role === "user"
                          ? "rounded-br-sm bg-[#C5050C] text-white"
                          : "rounded-bl-sm border border-zinc-200 bg-white"
                      }`}
                    >
                      {message.text}
                    </div>
                  </div>
                ))}

                {busy && (
                  <div role="status" className="flex items-center gap-2 text-xs text-zinc-500">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-200 border-t-[#C5050C]" />
                    {progress || "Working on your request..."}
                  </div>
                )}

                {candidates.length > 0 && (
                  <section className="space-y-3">
                    <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                      Suggested options
                    </h2>

                    {candidates.map((candidate, index) => (
                      <CandidateCard
                        key={candidate.id}
                        candidate={candidate}
                        index={index}
                        disabled={busy || status !== "candidates"}
                        onSelect={selectCandidate}
                      />
                    ))}
                  </section>
                )}

                {error && (
                  <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                    {error}
                  </div>
                )}

                {status === "done" && (
                  <div className="rounded-lg bg-green-50 p-3 text-xs font-medium text-green-700">
                    Demo task completed.
                  </div>
                )}
              </div>
            )}

            <div ref={bottomRef} />
          </main>

          <footer className="border-t border-zinc-200 bg-white p-3">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void sendMessage();
              }}
              className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 p-2 focus-within:border-[#C5050C]"
            >
              <input
                ref={inputRef}
                aria-label="Message Jev"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask Jev to schedule something..."
                className="min-w-0 flex-1 bg-transparent px-2 text-sm outline-none"
                disabled={busy}
              />

              <button
                type="submit"
                aria-label="Send message"
                disabled={busy || !input.trim()}
                className="rounded-lg bg-[#C5050C] px-3 py-2 text-sm font-bold text-white hover:bg-red-800 disabled:opacity-40"
              >
                Send
              </button>
            </form>

            <p className="mt-2 text-center text-[10px] text-zinc-500">
              Nothing is booked without your confirmation.
            </p>
          </footer>
        </>
      ) : (
        <main className="flex-1 overflow-y-auto p-4">
          <h2 className="text-xl font-bold capitalize">{page}</h2>
          <p className="mt-2 text-sm text-zinc-500">
            This section is under development.
          </p>
        </main>
      )}

      {selected && (
        <ConfirmDialog
          candidate={selected}
          onConfirm={() => void confirmBooking()}
          onCancel={cancelSelection}
        />
      )}
    </div>
  );
}
