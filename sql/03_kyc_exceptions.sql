CREATE OR REPLACE TABLE reporting.kyc_exceptions AS
SELECT x.customer_id, x.kyc_status, x.total_balance
FROM analytics.customer_360 x
WHERE x.kyc_status <> 'VERIFIED' AND x.total_balance > 10000;
