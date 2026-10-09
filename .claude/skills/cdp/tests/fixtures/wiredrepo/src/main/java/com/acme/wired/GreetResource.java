package com.acme.wired;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetResource {

    private final Greeter greeter;

    public GreetResource(Greeter greeter) {
        this.greeter = greeter;
    }

    @GetMapping("/greet")
    public String greet(String name) {
        return greeter.greet(name);
    }
}
