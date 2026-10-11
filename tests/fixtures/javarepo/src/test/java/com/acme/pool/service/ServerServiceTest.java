package com.acme.pool.service;

import com.acme.pool.repo.ServerRepository;

class ServerServiceTest {
    void registersAServer() {
        ServerService service = new ServerService(new ServerRepository());
        service.register("x");
    }

    void exposesPriority() {
        new ServerService(new ServerRepository()).getPriority();
    }
}
