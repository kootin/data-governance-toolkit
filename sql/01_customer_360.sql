CREATE OR REPLACE TABLE analytics.customer_360 AS
WITH acct AS (
    SELECT customer_id, count(*) AS accounts, sum(balance) AS total_balance
    FROM accounts GROUP BY customer_id
)
SELECT c.customer_id, c.segment, c.kyc_status, a.accounts, a.total_balance
FROM customers c LEFT JOIN acct a USING (customer_id);
