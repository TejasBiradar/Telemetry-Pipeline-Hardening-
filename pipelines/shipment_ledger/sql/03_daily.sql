-- Stage: daily — roll up cleaned shipments by warehouse and carrier.
CREATE TABLE daily AS
SELECT
    warehouse,
    carrier,
    COUNT(*) AS shipment_count,
    AVG(weight_kg) AS avg_weight_kg,
    SUM(weight_kg) AS total_weight_kg
FROM cleaned
GROUP BY warehouse, carrier;
