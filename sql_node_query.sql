-- Put this query or any other of your choice in Microsofr SQL Node

SELECT TOP 100
    b.booking_id,
    b.customer_id,
    CONCAT(c.first_name, ' ', c.last_name)       AS customer_name,
    c.email                                       AS customer_email,
    b.status,
    b.total_amount,
    b.currency,
    CONVERT(varchar(10), b.booking_created_at, 23) AS booking_date,  -- YYYY-MM-DD
    b.city,
    b.country_code,
    b.nights
FROM airbnb.fact_booking AS b
JOIN airbnb.dim_customer AS c
  ON c.customer_id = b.customer_id
WHERE b.total_amount > 2500
  AND c.email IS NOT NULL
ORDER BY b.booking_created_at DESC;