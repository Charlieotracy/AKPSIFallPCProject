import type {
  BackendEvent,
  Candidate,
  Module,
  TaskStatus,
} from "../../shared/types";

type Emit = (event: BackendEvent) => void;

const delay = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

function detectModule(message: string): Module {
  const text = message.toLowerCase();

  if (/ticket|football|basketball|badgers/.test(text)) {
    return "tickets";
  }

  if (/uhs|appointment|doctor|health/.test(text)) {
    return "uhs";
  }

  if (/exam|midterm|cbtf|quiz/.test(text)) {
    return "cbtf";
  }

  return "courses";
}

const demoLabels: Record<Module, string[]> = {
  cbtf: [
    "Thursday, 2:30 PM",
    "Thursday, 4:00 PM",
    "Friday, 10:00 AM",
  ],
  courses: [
    "Lecture 001 - Mon/Wed 11:00 AM",
    "Lecture 002 - Tue/Thu 2:30 PM",
    "Lecture 003 - Mon/Wed 3:30 PM",
  ],
  uhs: [
    "Thursday, 10:00 AM",
    "Friday, 1:30 PM",
    "Monday, 11:00 AM",
  ],
  tickets: [
    "Example listing - $25",
    "Example listing - $35",
    "Example listing - $45",
  ],
};

export async function mockSearch(
  message: string,
  emit: Emit
): Promise<void> {
  const taskId = crypto.randomUUID();
  const module = detectModule(message);

  const status = (value: TaskStatus) =>
    emit({
      type: "status",
      task_id: taskId,
      status: value,
    });

  status("ready");

  emit({
    type: "assistant_message",
    text: "I'll look for some options for you.",
  });

  await delay(500);
  status("searching");

  emit({
    type: "progress",
    task_id: taskId,
    step: 1,
    note: "Searching example availability...",
  });

  await delay(800);

  emit({
    type: "progress",
    task_id: taskId,
    step: 2,
    note: "Ranking example options...",
  });

  await delay(600);

  const candidates: Candidate[] = demoLabels[module].map(
    (label, index) => ({
      id: crypto.randomUUID(),
      task_id: taskId,
      label,
      starts_at: null,
      data: {
        module,
        demo: true,
        bookable: module !== "tickets",
      },
      fit: [0.98, 0.91, 0.84][index] ?? null,
    })
  );

  emit({
    type: "assistant_message",
    text: "Here are three example options. These are simulated results, not live availability.",
  });

  emit({
    type: "candidates",
    task_id: taskId,
    candidates,
  });

  status(module === "tickets" ? "done" : "candidates");
}

export async function mockBook(
  candidate: Candidate,
  confirmed: boolean,
  emit: Emit
): Promise<void> {
  if (!confirmed || candidate.data.bookable !== true) {
    throw new Error("Booking is not permitted.");
  }

  emit({
    type: "status",
    task_id: candidate.task_id,
    status: "executing",
  });

  emit({
    type: "progress",
    task_id: candidate.task_id,
    step: 3,
    note: "Simulating booking...",
  });

  await delay(1000);

  emit({
    type: "done",
    task_id: candidate.task_id,
    summary: `Demo booking completed: ${candidate.label}. No real reservation was made.`,
  });

  emit({
    type: "status",
    task_id: candidate.task_id,
    status: "done",
  });
}

