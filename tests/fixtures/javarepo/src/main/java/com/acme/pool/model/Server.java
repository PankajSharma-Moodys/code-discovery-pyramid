package com.acme.pool.model;

public class Server {
    public static final String DEFAULT_NAME = "srv";
    static int MAX_MAINTENANCE_MINUTES = 30;
    private final String name;
    private int hint;

    public Server(String name) {
        this.name = name;
    }

    Server() {
        this("anon");
    }

    public String getName() {
        return name;
    }

    int weight() {
        return name.length() + hint;
    }

    public Server withHint(int hint) {
        this.hint = hint;
        return this;
    }
}
