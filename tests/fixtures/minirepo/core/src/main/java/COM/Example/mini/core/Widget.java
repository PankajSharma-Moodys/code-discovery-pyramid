package com.example.mini.core;

import java.util.Objects;

/** Shared domain type. The directory says COM/Example; the package says com.example. */
public class Widget {

  private final String id;

  public Widget(String id) {
    this.id = id;
  }

  public String getId() {
    return id;
  }

  @Override
  public boolean equals(Object other) {
    return other instanceof Widget && Objects.equals(id, ((Widget) other).id);
  }
}
