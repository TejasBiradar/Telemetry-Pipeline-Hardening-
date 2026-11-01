-- Land every raw shipment, then clean, then roll up by carrier.
CREATE TABLE landed AS
SELECT shipment_id, warehouse, weight_g, carrier, lane, note
FROM raw;

CREATE TABLE cleaned AS
SELECT
    shipment_id,
    warehouse,
    weight_g / 1000.0 AS weight_kg,
    COALESCE(carrier, 'Other') AS carrier,
    lane,
    note
FROM landed
WHERE shipment_id IS NOT NULL
  AND weight_g > 0
  AND warehouse LIKE 'WH_%';

CREATE TABLE daily AS
SELECT
    carrier,
    COUNT(*) AS shipment_count,
    AVG(weight_kg) AS avg_weight_kg
FROM cleaned
GROUP BY carrier;
