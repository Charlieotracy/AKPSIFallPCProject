package com.jevuw.watch.enroll;

/** The unit students watch: an enrollment package. String form is "termCode:enrollmentClassNumber". */
public record PackageKey(String termCode, long enrollmentClassNumber) {

    public static PackageKey parse(String text) {
        int colon = text.indexOf(':');
        if (colon <= 0 || colon == text.length() - 1) {
            throw new IllegalArgumentException("Invalid package key: " + text);
        }
        try {
            return new PackageKey(text.substring(0, colon), Long.parseLong(text.substring(colon + 1)));
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Invalid package key: " + text, e);
        }
    }

    @Override
    public String toString() {
        return termCode + ":" + enrollmentClassNumber;
    }
}
