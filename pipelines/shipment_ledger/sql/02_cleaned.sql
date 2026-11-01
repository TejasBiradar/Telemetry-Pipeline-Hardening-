-- Stage: cleaned — drop null ids; convert grams to kilograms.
CREATE TABLE cleaned AS
SELECT
    shipment_id,
    warehouse,
    weight_g / 1000.0 AS weight_kg,
    carrier,
    lane,
    note
FROM landed
WHERE shipment_id IS NOT NULL;
