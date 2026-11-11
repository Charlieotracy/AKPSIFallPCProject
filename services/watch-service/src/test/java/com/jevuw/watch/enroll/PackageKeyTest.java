package com.jevuw.watch.enroll;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class PackageKeyTest {

    @Test
    void roundTripsThroughString() {
        PackageKey key = PackageKey.parse("1272:29465");

        assertThat(key).isEqualTo(new PackageKey("1272", 29465));
        assertThat(key).hasToString("1272:29465");
    }

    @Test
    void rejectsMalformedKeys() {
        assertThatThrownBy(() -> PackageKey.parse("1272")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> PackageKey.parse(":29465")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> PackageKey.parse("1272:abc")).isInstanceOf(IllegalArgumentException.class);
    }
}
