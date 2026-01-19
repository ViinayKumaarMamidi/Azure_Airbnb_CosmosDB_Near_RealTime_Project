# pip install azure-cosmos

from azure.cosmos import CosmosClient, PartitionKey
import random
from datetime import datetime, timedelta, timezone, date
from faker import Faker
import csv
import os
import time
from typing import List, Tuple


# ---------- Config ----------

DB_NAME = 'AirBnB'
CONTAINER_NAME = 'bookings'
COSMOS_URL = 'https://uswestcosmosdev.documents.azure.com:443/'
COSMOS_KEY = 'XoAsxA7PP25oVGepPBW8EHVbawEBvb0K6aI3GU5mrcGgTytmUCGqWtjg8ZOlr2O8hHX9ECTDn8QqACDbG44o5Q==' 

NUM_RECORDS = 500  # total confirmed bookings to publish
CANCEL_RATE_PCT = random.randint(2, 5)  # 2–5% will be cancelled after confirm
SLEEP_BETWEEN_WRITES_SEC = 0.01  # light throttling

# Cities with base nightly rate (USD) and country_code
CITY_CATALOG = [
	{"city": "New York", "country": "USA", "base": 180},
	{"city": "London", "country": "UK", "base": 170},
	{"city": "Paris", "country": "FRA", "base": 160},
	{"city": "Dubai", "country": "UAE", "base": 150},
	{"city": "Mumbai", "country": "IND", "base": 90},
	{"city": "Tokyo", "country": "JPN", "base": 140},
	{"city": "Sydney", "country": "AUS", "base": 130}
]

CHANNELS = ["app", "web", "partner"]
DEVICE_TYPES = ["iOS", "Android", "Web"]
CURRENCIES = ["USD", "EUR", "GBP", "AED", "INR", "JPY", "AUD"]
CANCEL_REASONS = [
	"guest_change_of_plans",
	"host_issue",
	"payment_issue",
	"weather",
	"overbooking"
]

fake = Faker()

# ---------- Cosmos client ----------
client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY)
database = client.create_database_if_not_exists(id=DB_NAME)
# Partition by booking_id for item-level updates and efficient cancellations
container = database.create_container_if_not_exists(
	id=CONTAINER_NAME,
	partition_key=PartitionKey(path="/booking_id")
)

# ---------- Helpers ----------

def load_customer_ids_2025(folder_path: str):
	"""Load customer_ids from base + delta 2025 files to ensure joinable keys for SCD2."""
	patterns = [
		"customer_data_2025_10_30_base.csv",
		"customer_data_2025_10_30_delta1.csv",
		"customer_data_2025_10_30_delta2.csv",
	]
	ids = []
	for name in patterns:
		path = os.path.join(folder_path, name)
		if not os.path.exists(path):
			continue
		with open(path, newline='') as csvfile:
			reader = csv.DictReader(csvfile)
			for row in reader:
				try:
					ids.append(int(row['customer_id']))
				except Exception:
					continue
	ids = sorted(set(ids))
	return ids or list(range(1, 101))

def pick_2025_dates():
	# booking_created_at in 2025, heavier in Jun–Aug and Dec
	season_months = [6, 7, 8, 12]
	if random.random() < 0.55:
		month = random.choice(season_months)
	else:
		month = random.randint(1, 12)
	day = random.randint(1, 28)
	booking_created_at = datetime(2025, month, day, random.randint(6, 22), random.randint(0, 59), tzinfo=timezone.utc)
	lead_time = int(random.triangular(7, 45, 28))
	checkin_date = (booking_created_at + timedelta(days=lead_time)).date()
	nights = max(1, int(random.triangular(1, 14, 3)))
	checkout_date = checkin_date + timedelta(days=nights)
	return booking_created_at, checkin_date, checkout_date, nights, lead_time

def price_components(city_row, nights: int, checkin: date):
	base = city_row["base"]
	peak_months = {6, 7, 8, 12}
	adj = 1.0
	if checkin.month in peak_months:
		adj += random.uniform(0.1, 0.3)
	if checkin.weekday() in (4, 5):  # Fri/Sat
		adj += random.uniform(0.05, 0.15)
	price_nightly = round(base * adj, 2)
	cleaning_fee = round(random.uniform(20, 80), 2)
	total_amount = round(price_nightly * nights + cleaning_fee, 2)
	return price_nightly, cleaning_fee, total_amount

# ---------- Publisher ----------

def generate_booking_doc(customer_id: int):
	city = random.choice(CITY_CATALOG)
	booking_created_at, checkin_date, checkout_date, nights, lead_time = pick_2025_dates()
	price_nightly, cleaning_fee, total_amount = price_components(city, nights, checkin_date)
	channel = random.choices(CHANNELS, weights=[0.6, 0.35, 0.05])[0]
	device = random.choices(DEVICE_TYPES, weights=[0.4, 0.4, 0.2])[0]

	booking_id = fake.uuid4()
	currency = random.choice(CURRENCIES)

	return {
		"id": booking_id,  # use booking_id as document id
		"booking_id": booking_id,
		"customer_id": str(customer_id),
		"listing_id": str(random.randint(100000, 999999)),
		"status": "Confirmed",
		"booking_created_at": booking_created_at.isoformat(),
		"checkin_date": checkin_date.isoformat(),
		"checkout_date": checkout_date.isoformat(),
		"nights": nights,
		"lead_time_days": lead_time,
		"guests_adults": max(1, int(random.triangular(1, 3, 2))),
		"guests_children": 1 if random.random() < 0.25 else 0,
		"guests_infants": 1 if random.random() < 0.05 else 0,
		"price_nightly": price_nightly,
		"cleaning_fee": cleaning_fee,
		"total_amount": total_amount,
		"currency": currency,
		"country_code": city["country"],
		"city": city["city"],
		"channel": channel,
		"device_type": device,
		"cancellation_ts": None,
		"cancellation_reason": None,
		"updated_at": datetime.now(timezone.utc).isoformat()
	}


def publish_confirmed():
	customer_csv_dir = os.path.join(
		os.path.dirname(__file__),
		"CustomerData"
	)
	customer_ids = load_customer_ids_2025(customer_csv_dir)
	print(f"Loaded {len(customer_ids)} 2025 customer keys from base+delta files")

	created_ids = []
	for _ in range(NUM_RECORDS):
		doc = generate_booking_doc(random.choice(customer_ids))
		container.upsert_item(doc)
		# Store (document id, partition key) where partition key is booking_id
		created_ids.append((doc['id'], doc['booking_id']))
		if SLEEP_BETWEEN_WRITES_SEC:
			time.sleep(SLEEP_BETWEEN_WRITES_SEC)

	print("Done: published confirmed bookings.")


# ---------- Maintenance: Update existing bookings to Cancelled ----------

def cancel_existing_bookings(sample_rate_pct: int = CANCEL_RATE_PCT, max_scan: int = 2000):
    """Query existing Confirmed bookings and mark a random sample as Cancelled.

    sample_rate_pct: percent of scanned confirmed bookings to cancel (1-100)
    max_scan: upper bound of documents to scan to avoid huge queries in dev
    """
    if sample_rate_pct <= 0:
        print("Skip: sample_rate_pct <= 0")
        return

    query = {
        "query": "SELECT c.id, c.booking_id FROM c WHERE c.status = @status",
        "parameters": [{"name": "@status", "value": "Confirmed"}],
    }

    results: List[Tuple[str, str]] = []
    for item in container.query_items(query=query, enable_cross_partition_query=True):
        # (id, partitionKey=booking_id)
        results.append((item["id"], item["booking_id"]))
        if len(results) >= max_scan:
            break

    if not results:
        print("No confirmed bookings found to cancel.")
        return

    k = max(1, int(len(results) * (sample_rate_pct / 100.0)))
    sample = random.sample(results, k)
    print(f"Cancelling {k} of {len(results)} scanned confirmed bookings…")

    for doc_id, pk in sample:
        container.patch_item(
            item=doc_id,
            partition_key=pk,
            patch_operations=[
                {"op": "add", "path": "/status", "value": "Cancelled"},
                {"op": "add", "path": "/cancellation_ts", "value": datetime.now(timezone.utc).isoformat()},
                {"op": "add", "path": "/cancellation_reason", "value": random.choice(CANCEL_REASONS)},
                {"op": "add", "path": "/updated_at", "value": datetime.now(timezone.utc).isoformat()},
            ],
        )
        if SLEEP_BETWEEN_WRITES_SEC:
            time.sleep(SLEEP_BETWEEN_WRITES_SEC)
    print("Done: patched cancellations on existing bookings.")

if __name__ == "__main__":
	publish_confirmed()
	# cancel_existing_bookings(2)
