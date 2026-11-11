package com.jevuw.watch.enroll;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Package status. Only OPEN has been seen in real data; CLOSED and WAITLISTED are unconfirmed guesses
 * (see docs/course-api.md). Anything else maps to UNKNOWN.
 */
public enum PackageAvailability {
    OPEN, CLOSED, WAITLISTED, UNKNOWN;

    private static final Logger log = LoggerFactory.getLogger(PackageAvailability.class);

    public static PackageAvailability fromApi(String status) {
        for (PackageAvailability value : values()) {
            if (value != UNKNOWN && value.name().equals(status)) {
                return value;
            }
        }
        log.warn("Unexpected package status from enroll API: '{}'", status);
        return UNKNOWN;
    }
}
