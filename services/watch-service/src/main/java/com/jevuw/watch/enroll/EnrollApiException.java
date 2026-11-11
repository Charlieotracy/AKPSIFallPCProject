package com.jevuw.watch.enroll;

/** The enroll API failed: HTTP error, timeout, or a response missing required fields. */
public class EnrollApiException extends RuntimeException {

    public EnrollApiException(String message) {
        super(message);
    }

    public EnrollApiException(String message, Throwable cause) {
        super(message, cause);
    }
}
