package com.acme.pool.service;

public interface Provisioner {
    int getPriority();

    default String label() {
        return "p" + getPriority();
    }
}
