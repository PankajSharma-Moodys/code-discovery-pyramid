package com.acme.pool.service;

import static com.acme.pool.service.Keys.WAIT;

public class Settings {
    private static final String LOCAL = "pool.local";

    public String size() {
        return System.getenv("POOL_SIZE");
    }

    public String home() {
        return System.getProperty(Keys.HOME, "/tmp");
    }

    public String mode() {
        return System.getenv().getOrDefault("POOL_MODE",
            "test");
    }

    public long timeout() {
        return Long.getLong(LOCAL, 5L) + Long.getLong(WAIT, 1L);
    }

    public String envName() {
        return System.getenv(Keys.ENV);
    }

    public String other(String name) {
        return System.getenv(name);
    }

    public String again() {
        return System.getProperty(Keys.HOME);
    }
}
