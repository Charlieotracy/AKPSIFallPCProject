package com.jevuw.watch.enroll;

import java.time.Instant;

/** Seat summary for one enrollment package, from packageEnrollmentStatus. */
public record PackageStatus(
        PackageKey packageKey,
        int availableSeats,
        int waitlistTotal,
        PackageAvailability status,
        Instant fetchedAt) {
}
