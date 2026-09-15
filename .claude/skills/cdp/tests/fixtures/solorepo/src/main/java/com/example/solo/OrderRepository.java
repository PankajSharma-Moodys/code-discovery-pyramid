package com.example.solo;

import javax.persistence.Entity;

@Entity
public class OrderRepository {

    public String findAll() {
        return "select * from orders";
    }
}
