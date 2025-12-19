import requests

LOGO_DEV_PUBLIC_KEY = 'pk_K96TtQYUTvy3hHXDyIEUqw'

def get_company_logo(company_name: str) -> str:
    """
    Returns the URL to the company logo using logo.dev.
    domain: company domain or name (like 'helpscout', 'zapier')
    """
    safe_name = company_name.lower().replace(" ", "")
    url = f"https://img.logo.dev/name/{safe_name}?token={LOGO_DEV_PUBLIC_KEY}&size=101&retina=true"
    # Optionally check if the logo exists
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return url
    except requests.RequestException:
        return ""  # return empty if fetching fails
