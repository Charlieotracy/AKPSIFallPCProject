package com.jevuw.watch.enroll;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.equalTo;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.getRequestedFor;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.github.tomakehurst.wiremock.junit5.WireMockExtension;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;

class EnrollApiClientTest {

    private static final String PATH = "/api/search/v2/enrollmentPackages/1272/320/006287";
    private static final CourseKey ECE_230 = new CourseKey("1272", "320", "006287");
    private static final Instant NOW = Instant.parse("2026-11-11T12:00:00Z");

    @RegisterExtension
    static WireMockExtension wireMock = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    private EnrollApiClient client(Duration readTimeout) {
        EnrollApiProperties properties = new EnrollApiProperties(
                wireMock.baseUrl(), Duration.ofSeconds(3), readTimeout);
        return new EnrollApiClient(properties, Clock.fixed(NOW, ZoneOffset.UTC));
    }

    private static String fixture(String name) throws IOException {
        try (InputStream in = EnrollApiClientTest.class.getResourceAsStream("/enroll/" + name)) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private void stubBody(String body) {
        wireMock.stubFor(get(urlEqualTo(PATH)).willReturn(aResponse()
                .withHeader("Content-Type", "application/json")
                .withBody(body)));
    }

    @Test
    void openFixtureGivesTwoOpenPackages() throws IOException {
        stubBody(fixture("packages-open.json"));

        List<PackageStatus> packages = client(Duration.ofSeconds(5)).fetchPackages(ECE_230);

        assertThat(packages).extracting(PackageStatus::packageKey)
                .containsExactly(PackageKey.parse("1272:35921"), PackageKey.parse("1272:29465"));
        assertThat(packages).extracting(PackageStatus::status).containsOnly(PackageAvailability.OPEN);
        assertThat(packages).extracting(PackageStatus::availableSeats).containsExactly(43, 14);
        assertThat(packages).extracting(PackageStatus::waitlistTotal).containsExactly(0, 0);
        assertThat(packages).extracting(PackageStatus::fetchedAt).containsOnly(NOW);
    }

    @Test
    void sendsClearUserAgent() throws IOException {
        stubBody(fixture("packages-open.json"));

        client(Duration.ofSeconds(5)).fetchPackages(ECE_230);

        wireMock.verify(getRequestedFor(urlEqualTo(PATH))
                .withHeader("User-Agent", equalTo("jev-uw-watch-service (student project)")));
    }

    @Test
    void fullFixtureGivesClosedWithNoSeats() throws IOException {
        stubBody(fixture("packages-full.json"));

        List<PackageStatus> packages = client(Duration.ofSeconds(5)).fetchPackages(ECE_230);

        assertThat(packages).extracting(PackageStatus::status).containsOnly(PackageAvailability.CLOSED);
        assertThat(packages).extracting(PackageStatus::availableSeats).containsOnly(0);
    }

    @Test
    void waitlistFixtureGivesWaitlistedWithWaitlistNumbers() throws IOException {
        stubBody(fixture("packages-waitlist.json"));

        List<PackageStatus> packages = client(Duration.ofSeconds(5)).fetchPackages(ECE_230);

        assertThat(packages).extracting(PackageStatus::status).containsOnly(PackageAvailability.WAITLISTED);
        assertThat(packages).extracting(PackageStatus::availableSeats).containsOnly(0);
        assertThat(packages).extracting(PackageStatus::waitlistTotal).containsOnly(3);
    }

    @Test
    void unknownStatusStringMapsToUnknownWithoutThrowing() throws IOException {
        stubBody(fixture("packages-open.json").replace("\"OPEN\"", "\"SOMETHING_NEW\""));

        List<PackageStatus> packages = client(Duration.ofSeconds(5)).fetchPackages(ECE_230);

        assertThat(packages).hasSize(2);
        assertThat(packages).extracting(PackageStatus::status).containsOnly(PackageAvailability.UNKNOWN);
    }

    @Test
    void serverErrorThrowsEnrollApiException() {
        wireMock.stubFor(get(urlEqualTo(PATH)).willReturn(aResponse().withStatus(500)));

        assertThatThrownBy(() -> client(Duration.ofSeconds(5)).fetchPackages(ECE_230))
                .isInstanceOf(EnrollApiException.class);
    }

    @Test
    void responseSlowerThanReadTimeoutThrowsEnrollApiException() throws IOException {
        wireMock.stubFor(get(urlEqualTo(PATH)).willReturn(aResponse()
                .withHeader("Content-Type", "application/json")
                .withBody(fixture("packages-open.json"))
                .withFixedDelay(1500)));

        assertThatThrownBy(() -> client(Duration.ofMillis(300)).fetchPackages(ECE_230))
                .isInstanceOf(EnrollApiException.class);
    }

    @Test
    void responseMissingRequiredFieldThrowsEnrollApiException() {
        stubBody("[{\"termCode\": \"1272\", \"enrollmentClassNumber\": 1}]");

        assertThatThrownBy(() -> client(Duration.ofSeconds(5)).fetchPackages(ECE_230))
                .isInstanceOf(EnrollApiException.class)
                .hasMessageContaining("packageEnrollmentStatus");
    }
}
