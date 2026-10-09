package com.acme.orders;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;
    private String sku;

    public OrderEntity(String sku) {
        this.sku = sku;
    }
}
