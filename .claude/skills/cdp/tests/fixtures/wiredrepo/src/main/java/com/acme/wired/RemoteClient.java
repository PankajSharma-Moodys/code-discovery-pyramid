package com.acme.wired;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class RemoteClient {

    @Value("${billing.url}")
    private String billingUrl;

    private final RestTemplate restTemplate;

    public RemoteClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String send(String name) {
        return restTemplate.exchange(
                billingUrl + "/v1/charges",
                HttpMethod.POST,
                null,
                String.class).getBody();
    }
}
