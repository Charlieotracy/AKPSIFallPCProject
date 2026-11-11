# UW–Madison course API notes (for the Watch Service)

Source: two responses captured by hand in a browser (cookies removed), term `1272`. We have **not**
called this API from code. Fixtures are in
[`services/watch-service/src/test/resources/enroll/`](../services/watch-service/src/test/resources/enroll/README.md).
Anything not seen in real data is marked **UNCONFIRMED**.

Base URL: `https://public.enroll.wisc.edu`. The API is unofficial and undocumented.

## 1. Course search (reference only)

`POST /api/search/v2`. The request body was not captured. The watcher does not need search.

Response (`search-v2.json`): `found`, `success`, `hits[]`. Per hit we care about:

| Field | JSON path | Example |
|---|---|---|
| Term code | `hits[].termCode` | `1272` |
| Course id | `hits[].courseId` | `006287` |
| Subject code | `hits[].subject.subjectCode` | `320` |
| Subject abbreviation | `hits[].subject.shortDescription` | `E C E` |
| Catalog number | `hits[].catalogNumber` | `230` |
| Title / designation | `hits[].title`, `hits[].courseDesignation` | `Circuit Analysis`, `E C E 230` |

`termCode` + `subjectCode` + `courseId` are exactly the three path parameters of the next request.

## 2. Enrollment packages (what the watcher polls)

`GET /api/search/v2/enrollmentPackages/{termCode}/{subjectCode}/{courseId}`,
e.g. `/api/search/v2/enrollmentPackages/1272/320/006287` (E C E 230).

Returns a JSON **array** of enrollment packages: **all** packages for the course in one request, so
we group polling by course (`CourseKey`), not by package.

### Enrollment packages

An enrollment package is what a student actually enrolls in: a lecture, or a lecture plus a
discussion/lab. Example (E C E 230):

| `enrollmentClassNumber` | `enrollmentPackageUniqueId.packageId` | Sections in package |
|---|---|---|
| 35921 | `002` | LEC 002 (35921) |
| 29465 | `001-301` | LEC 001 (18730) + DIS 301 (29465) |

For package 29465 the `enrollmentClassNumber` is the **discussion's** class number, not the
lecture's (18730, which appears in `autoEnrollClasses`, a field we do not keep).

### Fields we use

| Meaning | JSON path (per package) |
|---|---|
| Package id (string form of class number) | `id` |
| Term / subject / course / catalog | `termCode`, `subjectCode`, `courseId`, `catalogNumber` |
| Enrollment class number | `enrollmentClassNumber` |
| Package status | `packageEnrollmentStatus.status` |
| Seats available in package | `packageEnrollmentStatus.availableSeats` |
| Waitlist size for package | `packageEnrollmentStatus.waitlistTotal` |
| Package identity | `enrollmentPackageUniqueId.{termCode,subjectCode,catalogNumber,sessionCode,packageId}` |
| Document id | `docId`, e.g. `enrollmentPackage-1272-A1-320-230-001-301` |
| Section class number | `sections[].classUniqueId.classNumber` |
| Section type / number | `sections[].type` (`LEC`, `DIS` seen), `sections[].sectionNumber` |
| Capacity | `sections[].enrollmentStatus.capacity` |
| Enrolled | `sections[].enrollmentStatus.currentlyEnrolled` |
| Open seats | `sections[].enrollmentStatus.openSeats` |
| Waitlist capacity / size | `sections[].enrollmentStatus.waitlistCapacity`, `.waitlistCurrentSize` |
| Open waitlist spots | `sections[].enrollmentStatus.openWaitlistSpots` |
| Meetings | `sections[].classMeetings[].{meetingType,meetingTimeStart,meetingTimeEnd,meetingDaysList}` |

The real response also has a package-level `enrollmentStatus` (same shape as the section one; in the
sample it equals the enrollment-class section's) and `enrollmentOptions.waitlist`. We do not use them yet.

Real values seen: package 35921 `availableSeats` 43 (capacity 100, enrolled 57, no waitlist);
package 29465 `availableSeats` 14 (both sections capacity 100, enrolled 86; waitlist capacity 20 on the
lecture and 40 on the discussion, both empty). Here `availableSeats` equals the sections'
`openSeats`; how it is computed when sections differ is **UNCONFIRMED**.

## Watch key

`termCode:enrollmentClassNumber`, e.g. `1272:29465`. To know which request to make, store
`subjectCode` and `courseId` alongside the key (with `termCode` they form the `CourseKey`).

## Term code

`1272` in all captured data. Dates in the data (classes start 2026-09-02) indicate Fall 2026. The
pattern (`1` + year digits + season digit, with `2` = fall) is **UNCONFIRMED** from our data alone.

## Status values

| `packageEnrollmentStatus.status` | Status |
|---|---|
| `OPEN` | Confirmed (seen in both packages) |
| `CLOSED`, `WAITLISTED` | **UNCONFIRMED guesses** used in synthetic fixtures. Map anything unexpected to `UNKNOWN`. |

## `meetingTimeStart` / `meetingTimeEnd` units

Integers that look like **milliseconds since midnight** (e.g. `73800000` = 20.5 h, `69600000` = 19 h 20 m).
**UNCONFIRMED**: the time zone. Read as UTC, `69600000` is 1:20 PM at UTC-6 but 2:20 PM at UTC-5, and
Madison is on UTC-5 (CDT) in September, so "1:20 PM Central" is not certain. The exam meeting
(`74700000` to `81900000`, 2 h) does not match an obvious local time either. We do not need meeting
times for seat watching; do not rely on them until checked against the website.
Other date fields (`startDate`, `endDate`, `examDate`) are epoch milliseconds.

## Surprising things

- `classMeetings` mixes `Class` and `Exam` entries, and the lecture in package 29465 has two `Class` meetings (different rooms, same time).
- Capacity is not fixed: a CS department footnote says some courses add seats gradually during enrollment, so `capacity` can increase between polls. Do not treat a capacity change as an error; alert when `availableSeats` goes from 0 to above 0.
- Rate limits, caching headers and required request headers are **unknown**: we have not made any request.

## Open risks

- **CloudFront returns 403 to non-browser (server) requests.** The Watch Service cannot reach the API today.
- **Awaiting UW DoIT permission** to poll this API. Do not run the service against the real site until we have it.
- **Unofficial API**: undocumented and may change shape or disappear without notice (the team plan listed `v1`; `v2` is what the site uses now).
- **Capacity and seat counts change mid-enrollment**, including capacity increases. Polling frequency matters for useful alerts but must stay polite.
- **Unconfirmed statuses**: only `OPEN` has been observed; `CLOSED`/`WAITLISTED` are guesses.
- **Unconfirmed time zone** for meeting times.
