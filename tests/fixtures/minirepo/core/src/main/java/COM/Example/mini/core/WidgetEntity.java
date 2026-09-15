package com.example.mini.core;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "widget")
public class WidgetEntity {

  @Id private Long id;

  @Column(name = "display_name")
  private String displayName;

  public Long getId() {
    return id;
  }
}
