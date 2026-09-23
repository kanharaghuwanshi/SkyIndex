import json
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent / '.env')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL:
    raise RuntimeError('SUPABASE_URL is missing from .env')
if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError('SUPABASE_SERVICE_ROLE_KEY is missing from .env')

# Use the real validated T+45 normalized SpiceJet output.
source_file = Path(__file__).resolve().parent / 'spicejet_data' / 'DEL_BOM_T45.json'
if not source_file.exists():
    raise FileNotFoundError(f'Not found: {source_file}')

quotes = json.loads(source_file.read_text(encoding='utf-8'))
if not quotes:
    raise RuntimeError('DEL_BOM_T45.json contains no quotes')

q = quotes[0]

row = {
    'collected_at': q.get('collected_at'),
    'collection_date': q.get('collection_date'),
    'origin': q.get('origin'),
    'destination': q.get('destination'),
    'airline': q.get('airline'),
    'flight_number': q.get('flight_number'),
    'travel_date': q.get('travel_date'),
    'lead_time': q.get('lead_time'),
    'departure_time': q.get('departure_time'),
    'arrival_time': q.get('arrival_time'),
    'duration_minutes': q.get('duration_minutes'),
    'stops': q.get('stops'),
    'fare_class': q.get('fare_class'),
    'fare_class_of_service': q.get('fare_class_of_service'),
    'fare_code': q.get('fare_code'),
    'product_class': q.get('product_class'),
    'base_fare': q.get('base_fare'),
    'taxes': q.get('taxes'),
    'udf': q.get('udf'),
    'fees': q.get('fees'),
    'convenience_fee': q.get('convenience_fee'),
    'service_fee': q.get('service_fee'),
    'other_charges': q.get('other_charges'),
    'total_fare': q.get('total_fare'),
    'currency': q.get('currency', 'INR'),
    'availability': q.get('availability'),
    'source': q.get('source', 'spicejet'),
    'quote_key': q.get('quote_key'),
    'fee_breakdown': q.get('fee_breakdown'),
    'segments': q.get('segments'),
    'breakdown_match': q.get('breakdown_match'),
}

required = ['collection_date', 'origin', 'destination', 'airline', 'flight_number', 'travel_date', 'total_fare', 'quote_key']
missing = [k for k in required if row.get(k) in (None, '')]
if missing:
    raise RuntimeError(f'Missing required values: {missing}')

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Avoid inserting the same test observation twice.
existing = (
    client.table('airfare_quotes')
    .select('id,quote_key,collection_date,total_fare')
    .eq('collection_date', row['collection_date'])
    .eq('quote_key', row['quote_key'])
    .limit(1)
    .execute()
)

if existing.data:
    print('ALREADY EXISTS')
    print(existing.data[0])
else:
    result = client.table('airfare_quotes').insert(row).execute()
    if not result.data:
        raise RuntimeError('Insert returned no row')
    print('INSERT SUCCESS')
    print(result.data[0])

# Read it back from DB to verify the saved fare breakup.
check = (
    client.table('airfare_quotes')
    .select('id,origin,destination,airline,flight_number,travel_date,lead_time,base_fare,taxes,udf,fees,convenience_fee,service_fee,other_charges,total_fare,quote_key,breakdown_match')
    .eq('collection_date', row['collection_date'])
    .eq('quote_key', row['quote_key'])
    .limit(1)
    .execute()
)

if not check.data:
    raise RuntimeError('Row was not found during read-back verification')

print('READ-BACK VERIFIED')
print(json.dumps(check.data[0], indent=2, default=str))
