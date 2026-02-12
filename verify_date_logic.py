import os
import django
from datetime import datetime, timedelta
from dateutil import parser
from django.utils import timezone
from django.conf import settings

# Configure minimal Django settings if not already configured
if not settings.configured:
    settings.configure(USE_TZ=True, TIME_ZONE='UTC')

django.setup()

def check_date_logic():
    print("Checking date logic...")
    
    # 1. Parsing a date string (simulating what happens in utils.parse_date)
    date_str = "2023-01-01"
    parsed = parser.parse(date_str)
    print(f"Parsed '{date_str}': {parsed}, type: {type(parsed)}, tzinfo: {parsed.tzinfo}")
    
    # 2. Current time
    now = timezone.now()
    print(f"Now: {now}, tzinfo: {now.tzinfo}")
    
    # 3. Calculate 5 months ago
    five_months_ago = now - timedelta(days=150)
    print(f"5 months ago: {five_months_ago}")
    
    # 4. Compare
    try:
        if parsed < five_months_ago:
            print("Comparison worked: Date is older than 5 months.")
        else:
            print("Comparison worked: Date is NOT older than 5 months.")
    except TypeError as e:
        print(f"Comparison FAILED: {e}")
        
        # Rewrite logic to handle timezone awareness
        if timezone.is_aware(parsed):
            parsed_aware = parsed
        else:
            parsed_aware = timezone.make_aware(parsed, timezone.get_current_timezone())
            
        print(f"Made aware: {parsed_aware}, tzinfo: {parsed_aware.tzinfo}")
        
        if parsed_aware < five_months_ago:
             print("Aware comparison worked: Date is older than 5 months.")
        else:
             print("Aware comparison worked: Date is NOT older than 5 months.")

if __name__ == "__main__":
    check_date_logic()
