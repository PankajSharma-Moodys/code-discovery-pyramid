package com.acme.wired;

import com.acme.wired.store.*;
import org.springframework.stereotype.Service;

@Service
public class GreeterImpl implements Greeter {

    private final RemoteClient remote;
    private final AuditStore audit = new AuditStore();

    public GreeterImpl(RemoteClient remote) {
        this.remote = remote;
    }

    @Override
    public String greet(String name) {
        audit.record(name);
        return remote.send(name);
    }
}
