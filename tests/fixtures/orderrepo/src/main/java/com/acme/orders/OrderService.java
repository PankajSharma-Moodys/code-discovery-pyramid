package com.acme.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderEntity placeOrder(OrderRequest request) {
        OrderEntity order = new OrderEntity(request.getSku());
        return repository.save(order);
    }
}
