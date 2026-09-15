package com.example.solo;

import javax.ws.rs.GET;
import javax.ws.rs.Path;

@Path("/v1/orders")
public class OrderResource {

    private final OrderRepository repository;

    public OrderResource(OrderRepository repository) {
        this.repository = repository;
    }

    @GET
    public String list() {
        return repository.findAll();
    }
}
