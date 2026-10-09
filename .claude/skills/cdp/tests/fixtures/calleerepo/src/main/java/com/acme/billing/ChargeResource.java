package com.acme.billing;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1")
public class ChargeResource {

    @PostMapping("/charges")
    public String charge(String orderId) {
        return orderId;
    }
}
