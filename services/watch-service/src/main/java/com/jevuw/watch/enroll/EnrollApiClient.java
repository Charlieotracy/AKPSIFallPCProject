package com.jevuw.watch.enroll;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Fetches enrollment packages for one course. One request returns all packages of the course, so
 * callers group polling by {@link CourseKey}. No retries or scheduling here.
 */
@Component
public class EnrollApiClient {

    static final String USER_AGENT = "jev-uw-watch-service (student project)";

    private final RestClient restClient;
    private final Clock clock;

    public EnrollApiClient(EnrollApiProperties properties, Clock clock) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(properties.connectTimeout());
        requestFactory.setReadTimeout(properties.readTimeout());
        this.restClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .defaultHeader(HttpHeaders.USER_AGENT, USER_AGENT)
                .defaultHeader(HttpHeaders.ACCEPT, "application/json")
                .build();
        this.clock = clock;
    }

    public List<PackageStatus> fetchPackages(CourseKey key) {
        JsonNode body;
        try {
            body = restClient.get()
                    .uri("/api/search/v2/enrollmentPackages/{term}/{subject}/{course}",
                            key.termCode(), key.subjectCode(), key.courseId())
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            throw new EnrollApiException("Enroll API request failed for " + key, e);
        }
        if (body == null || !body.isArray()) {
            throw new EnrollApiException("Expected a JSON array of packages for " + key);
        }
        Instant fetchedAt = clock.instant();
        List<PackageStatus> result = new ArrayList<>();
        for (JsonNode pkg : body) {
            result.add(toPackageStatus(pkg, fetchedAt));
        }
        return result;
    }

    private static PackageStatus toPackageStatus(JsonNode pkg, Instant fetchedAt) {
        String termCode = requiredText(pkg, "termCode");
        long classNumber = requiredNode(pkg, "enrollmentClassNumber").asLong();
        JsonNode status = requiredNode(pkg, "packageEnrollmentStatus");
        return new PackageStatus(
                new PackageKey(termCode, classNumber),
                requiredNode(status, "availableSeats").asInt(),
                requiredNode(status, "waitlistTotal").asInt(),
                PackageAvailability.fromApi(requiredText(status, "status")),
                fetchedAt);
    }

    private static JsonNode requiredNode(JsonNode parent, String field) {
        JsonNode node = parent.get(field);
        if (node == null || node.isNull()) {
            throw new EnrollApiException("Response is missing required field '" + field + "'");
        }
        return node;
    }

    private static String requiredText(JsonNode parent, String field) {
        return requiredNode(parent, field).asText();
    }
}
