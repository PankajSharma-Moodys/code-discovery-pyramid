package com.acme.pool.service;

import com.acme.pool.model.Server;
import java.util.List;

public abstract class HelperService {
    protected List<Server> getServersForStaticPool() {
        return List.of(new Server("a"));
    }

    public void setServerHint(Server server, int hint) {
        server.withHint(hint);
    }

    static String normalise(String raw) {
        return raw.trim();
    }
}
