create schema airbnb;

-- Create customer dim table
IF OBJECT_ID('airbnb.dim_customer') IS NOT NULL DROP TABLE airbnb.dim_customer;
CREATE TABLE airbnb.dim_customer (
	customer_id INT NOT NULL,
	first_name NVARCHAR(100) NOT NULL,
	last_name NVARCHAR(100) NOT NULL,
	email NVARCHAR(255) NOT NULL,
	phone_number NVARCHAR(50) NULL,
	address NVARCHAR(255) NULL,
	city NVARCHAR(100) NULL,
	state NVARCHAR(64) NULL,
	country NVARCHAR(64) NULL,
	zip_code NVARCHAR(20) NULL,
	signup_date DATE NULL,
	last_login DATETIME2 NULL,
	total_bookings INT NULL,
	total_spent DECIMAL(14,2) NULL,
	preferred_language NVARCHAR(32) NULL,
	referral_code NVARCHAR(64) NULL,
	account_status NVARCHAR(32) NULL
);

-- Create bookings fact table
IF OBJECT_ID('airbnb.fact_booking') IS NOT NULL DROP TABLE airbnb.fact_booking;
CREATE TABLE airbnb.fact_booking (
	booking_id NVARCHAR(64) NOT NULL,
	customer_id INT NOT NULL,
	listing_id NVARCHAR(64) NOT NULL,
	status NVARCHAR(16) NOT NULL,
	booking_created_at DATE NOT NULL,
	checkin_date DATE NOT NULL,
	checkout_date DATE NOT NULL,
	nights INT NOT NULL,
	lead_time_days INT NULL,
	guests_adults INT NOT NULL,
	guests_children INT NOT NULL,
	guests_infants INT NOT NULL,
	price_nightly DECIMAL(12,2) NOT NULL,
	cleaning_fee DECIMAL(12,2) NOT NULL,
	total_amount DECIMAL(14,2) NOT NULL,
	currency NVARCHAR(8) NOT NULL,
	country_code NVARCHAR(8) NULL,
	city NVARCHAR(100) NULL,
	channel NVARCHAR(16) NULL,
	device_type NVARCHAR(16) NULL,
	cancellation_ts DATETIME2 NULL,
	cancellation_reason NVARCHAR(64) NULL,
	updated_at DATETIME2 NULL
);

-- Create country level aggregations
CREATE TABLE airbnb.BookingCustomerAggregation (
    country NVARCHAR(100),
    total_bookings BIGINT,
    confirmed_bookings BIGINT,
    cancelled_bookings BIGINT,
    total_amount DECIMAL(18,2),
    confirmed_amount DECIMAL(18,2),
    cancelled_amount DECIMAL(18,2),
    cancellation_rate FLOAT,
    last_booking_date DATETIME2,
    first_booking_date DATETIME2,
    avg_amount FLOAT,
    confirmed_avg_amount FLOAT,
    cancelled_avg_amount FLOAT,
    min_amount DECIMAL(18,2),
    max_amount DECIMAL(18,2),
    distinct_customers BIGINT,
    avg_stay_duration FLOAT
)
WITH (DISTRIBUTION = ROUND_ROBIN);

-- Create stored procedure to popluate aggregation table after each run
CREATE PROCEDURE airbnb.BookingAggregation
AS
BEGIN
    TRUNCATE TABLE airbnb.BookingCustomerAggregation;

    INSERT INTO airbnb.BookingCustomerAggregation
    SELECT 
        c.country,
        COUNT_BIG(*) AS total_bookings,
        SUM(CASE WHEN b.status = 'Confirmed' THEN 1 ELSE 0 END) AS confirmed_bookings,
        SUM(CASE WHEN b.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_bookings,
        SUM(ISNULL(b.total_amount, 0)) AS total_amount,
        SUM(CASE WHEN b.status = 'Confirmed' THEN ISNULL(b.total_amount, 0) ELSE 0 END) AS confirmed_amount,
        SUM(CASE WHEN b.status = 'Cancelled' THEN ISNULL(b.total_amount, 0) ELSE 0 END) AS cancelled_amount,
        CASE WHEN COUNT_BIG(*) = 0 THEN 0.0 
             ELSE CAST(SUM(CASE WHEN b.status = 'Cancelled' THEN 1 ELSE 0 END) AS FLOAT) 
                  / CAST(COUNT_BIG(*) AS FLOAT) END AS cancellation_rate,
        MAX(b.booking_created_at) AS last_booking_date,
        MIN(b.booking_created_at) AS first_booking_date,
        AVG(CAST(ISNULL(b.total_amount, 0) AS FLOAT)) AS avg_amount,
        AVG(CASE WHEN b.status = 'Confirmed' THEN CAST(ISNULL(b.total_amount, 0) AS FLOAT) END) AS confirmed_avg_amount,
        AVG(CASE WHEN b.status = 'Cancelled' THEN CAST(ISNULL(b.total_amount, 0) AS FLOAT) END) AS cancelled_avg_amount,
        MIN(ISNULL(b.total_amount, 0)) AS min_amount,
        MAX(ISNULL(b.total_amount, 0)) AS max_amount,
        COUNT(DISTINCT b.customer_id) AS distinct_customers,
        AVG(CAST(ISNULL(b.nights, 0) AS FLOAT)) AS avg_stay_duration
    FROM 
        airbnb.fact_booking b
    JOIN 
        airbnb.dim_customer c ON b.customer_id = c.customer_id
    GROUP BY 
        c.country;
END;
