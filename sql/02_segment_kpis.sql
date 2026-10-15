CREATE OR REPLACE TABLE analytics.segment_kpis AS
SELECT segment, count(*) AS customers, sum(total_balance) AS aum
FROM analytics.customer_360 GROUP BY segment;
