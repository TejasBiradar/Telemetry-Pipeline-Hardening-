-- Stage: landed — raw shipment rows as received.
CREATE TABLE landed AS
SELECT
    shipment_id,
    warehouse,
    weight_g,
    carrier,
    lane,
    note
FROM raw;
