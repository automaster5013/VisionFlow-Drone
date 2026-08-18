ALTER TABLE operator_user
    ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT TRUE AFTER enabled;
