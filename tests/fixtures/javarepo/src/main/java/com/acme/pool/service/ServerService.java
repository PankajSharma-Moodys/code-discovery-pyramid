package com.acme.pool.service;

import com.acme.pool.model.Server;
import com.acme.pool.repo.ServerRepository;
import java.util.List;
import java.util.Optional;

public class ServerService extends HelperService implements Provisioner {
    private final ServerRepository repo;

    public ServerService(ServerRepository repo) {
        this.repo = repo;
    }

    public int getPriority() {
        return 1;
    }

    public void setServerHintApplied(Server server) {
        setServerHint(server, 2);
    }

    public int register(String name) {
        List<Server> pool = getServersForStaticPool();
        List<Server> again = this.getServersForStaticPool();
        int length = repo.find(name).getName().length();
        Optional<Server> first = repo.findAll().stream().findFirst();
        repo.findAll().get(0).withHint(3).getName();
        String clean = HelperService.normalise(name);
        return length + pool.size() + again.size() + clean.length() + first.get().getName().length();
    }

    public List<Server> byName(List<String> names) {
        names.forEach(this::touch);
        return names.stream().map(repo::find).toList();
    }

    private void touch(String name) {
        repo.find(name);
    }
}
