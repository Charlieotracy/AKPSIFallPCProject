package com.jevuw.watch.enroll;

/** Identifies one course; these are the three path parameters of the enrollmentPackages request. */
public record CourseKey(String termCode, String subjectCode, String courseId) {
}
