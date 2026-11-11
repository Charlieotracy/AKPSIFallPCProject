# Enroll API fixtures

| File | Origin | Notes |
|---|---|---|
| `packages-open.json` | **Real** capture (E C E 230, term 1272), trimmed | Both packages `OPEN`. Instructors, textbooks, buildings, footnotes removed. |
| `packages-full.json` | **SYNTHETIC** | Copy of `packages-open.json` with seat numbers changed. |
| `packages-waitlist.json` | **SYNTHETIC** | Copy of `packages-open.json` with seat numbers changed. |
| `search-v2.json` | **Real** capture, trimmed | Reference only; the watcher does not use search. |

## Synthetic fixtures

- The status strings `"CLOSED"` and `"WAITLISTED"` are **UNCONFIRMED guesses**. Only `"OPEN"` has been
  seen in real data. Replace these fixtures with real captures when we have them.
- `packages-full.json`: all `availableSeats`/`openSeats`/`openWaitlistSpots` are 0, status `CLOSED`.
  `waitlistTotal` for package 29465 is set to 40 (the waitlist size of that package's enrollment-class
  section); how the real API computes `waitlistTotal` is unconfirmed.
- `packages-waitlist.json`: 0 seats, `waitlistCurrentSize` 3, open waitlist spots > 0, status `WAITLISTED`.
  Package 35921 has no waitlist in the real data (`waitlistCapacity` 0); the synthetic file gives it
  a 20-spot waitlist so both packages exercise the WAITLISTED path.
- Numbers are internally consistent: `openSeats = capacity - currentlyEnrolled`,
  `openWaitlistSpots = waitlistCapacity - waitlistCurrentSize`.

Raw captures live in `raw/` (git-ignored; they contain instructor names and emails).
