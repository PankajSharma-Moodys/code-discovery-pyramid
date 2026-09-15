CREATE TABLE widget (
  id BIGINT PRIMARY KEY,
  display_name VARCHAR(200) NOT NULL
);

CREATE INDEX idx_widget_display_name ON widget (display_name);
