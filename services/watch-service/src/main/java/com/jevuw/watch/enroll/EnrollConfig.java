package com.jevuw.watch.enroll;

import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(EnrollApiProperties.class)
class EnrollConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
