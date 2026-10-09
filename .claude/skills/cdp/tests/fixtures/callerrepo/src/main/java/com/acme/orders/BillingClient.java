package com.acme.orders;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class BillingClient {

    private final RestTemplate restTemplate;

    public BillingClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String charge(String orderId) {
        return restTemplate.postForObject("http://billing/v1/charges", orderId, String.class);
    }
}
