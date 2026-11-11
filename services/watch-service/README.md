# Watch Service

Java 21 / Spring Boot service that will poll UW–Madison course seat data and alert students when a
seat opens in a section they are watching.

**Status:** skeleton plus an enroll API client. There is no scheduling, database schema, or alerting
yet. The client is only exercised against saved fixtures: UW's CloudFront currently returns 403 to
non-browser clients and we are awaiting DoIT permission. **Do not point the service at the real
site until that is resolved.** Details and open risks: [docs/course-api.md](../../docs/course-api.md).

## What exists

- `com.jevuw.watch.enroll`: `EnrollApiClient.fetchPackages(CourseKey)` calls
  `GET {enroll.api.base-url}/api/search/v2/enrollmentPackages/{term}/{subject}/{course}` and returns
  `PackageStatus` records (watch key `termCode:enrollmentClassNumber`, e.g. `1272:29465`).
- Flyway baseline migration, Actuator health endpoint.

## Run locally

Requires Docker.

```
cd services/watch-service
docker compose up --build
curl localhost:8080/actuator/health     # {"status":"UP",...}
```

Configuration comes from environment variables (defaults in `application.yml`):

| Variable | Default |
|---|---|
| `DB_URL` | `jdbc:postgresql://localhost:5432/watch` |
| `DB_USER` / `DB_PASSWORD` | `watch` / `watch` |
| `ENROLL_API_BASE_URL` | `https://public.enroll.wisc.edu` |

## Run tests

Requires Java 21 and a running Docker daemon (the context test uses Testcontainers Postgres).

```
cd services/watch-service
./gradlew test
```

API client tests use WireMock with the fixtures in `src/test/resources/enroll/` and never contact UW.
See that folder's [README](src/test/resources/enroll/README.md) for which fixtures are real and which
are synthetic.

## CI

`.github/workflows/watch-service.yml` runs `./gradlew test` on pushes and pull requests that touch
this folder.
