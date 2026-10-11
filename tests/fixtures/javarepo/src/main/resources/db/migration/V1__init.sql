-- CREATE TABLE commented_out (id int);
CREATE TABLE ${db_schema}.QRTZ_LOCKS (
  lock_name VARCHAR(40) NOT NULL
);
/* ALTER TABLE ignored_in_block ADD x int; */
CREATE TABLE ${db_schema}.server (id BIGINT PRIMARY KEY);
ALTER TABLE ${db_schema}.server ADD hint INT;
