package com.acme.pool.repo;

import com.acme.pool.model.Server;
import java.util.List;

public class ServerRepository {
    public Server find(String name) {
        return new Server(name);
    }

    public List<Server> findAll() {
        return List.of(find("x"));
    }
}
