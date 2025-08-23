import json
import copy
from urllib.parse import urlparse

# --- Configuration ---

# MIME types to generally filter out (unless they set a cookie).
MIME_TYPE_BLOCKLIST = {
    'text/css',
    'text/html',
    'application/javascript',
    'application/x-javascript',
    'font/woff',
    'font/woff2',
    'image/',
    'text/plain'
}

# Response headers to KEEP. We will now keep ALL request headers.
RESPONSE_HEADER_WHITELIST = {
    'content-type',
    'set-cookie',
    'location'
}


def extract_etld_plus_one(host: str) -> str:
    """Return a naive eTLD+1 (last two labels) from a hostname, stripping any port."""
    if not host:
        return ""
    if ':' in host:
        host = host.split(':', 1)[0]
    parts = host.split('.')
    if len(parts) >= 2:
        return f"{parts[-2]}.{parts[-1]}"
    return host


def get_primary_domain(har_data: dict) -> str:
    """Heuristically determines the primary domain for filtering.

    Strategy:
    1) If pages[0].title is a URL, use its eTLD+1.
    2) Otherwise, score all entry hostnames, favoring responses with text/html and Set-Cookie.
    3) Fallback to the first entry's hostname.
    """
    try:
        page_title = har_data['log']['pages'][0].get('title', '')
    except (IndexError, KeyError, TypeError):
        page_title = ''

    if isinstance(page_title, str) and page_title.startswith('http'):
        parsed = urlparse(page_title)
        return extract_etld_plus_one(parsed.netloc)

    # Score candidate domains from entries
    domain_score = {}
    try:
        entries = har_data.get('log', {}).get('entries', [])
    except AttributeError:
        entries = []

    for entry in entries[:500]:  # limit for performance on very large HARs
        request = entry.get('request', {})
        response = entry.get('response', {})
        req_url = request.get('url', '')
        host = urlparse(req_url).netloc
        domain = extract_etld_plus_one(host)
        if not domain:
            continue

        score = 1
        mime_type = response.get('content', {}).get('mimeType', '') or ''
        if isinstance(mime_type, str) and mime_type.startswith('text/html'):
            score += 5
        has_set_cookie = any(
            h.get('name', '').lower() == 'set-cookie' for h in response.get('headers', [])
        )
        if has_set_cookie:
            score += 4
        if request.get('method') == 'GET':
            score += 1

        domain_score[domain] = domain_score.get(domain, 0) + score

    if domain_score:
        return max(domain_score.items(), key=lambda kv: kv[1])[0]

    # Final fallback to first entry
    try:
        first_url = har_data['log']['entries'][0]['request']['url']
        return extract_etld_plus_one(urlparse(first_url).netloc)
    except (IndexError, KeyError, TypeError):
        print("Warning: Could not determine primary domain. Filtering may be less effective.")
        return ""


def is_blocked_mimetype(mime_type: str) -> bool:
    """Checks if a MIME type is in our blocklist."""
    if not mime_type:
        return False
    for blocked in MIME_TYPE_BLOCKLIST:
        if mime_type.startswith(blocked):
            return True
    return False


def truncate_text(value: str, threshold: int = 2000, keep: int = 1000) -> str:
    """If value length exceeds threshold, truncate to keep chars and append marker."""
    if not isinstance(value, str):
        return value
    if len(value) > threshold:
        return value[:keep] + " *TRUNCATED*"
    return value


def filter_har_data(har_data: dict) -> dict:
    """
    Filters a HAR dictionary, ensuring that critical session-initiating
    requests and all their original request headers are preserved.
    """
    primary_domain = get_primary_domain(har_data)
    print(f"Identified primary domain: {primary_domain}")

    new_har_data = copy.deepcopy(har_data)
    filtered_entries = []

    for entry in har_data['log']['entries']:
        request = entry.get('request', {})
        response = entry.get('response', {})
        req_url = request.get('url', '')

        # Determine if response sets any cookie (used both for keeping and whitelisting blocked types)
        has_set_cookie = any(
            h.get('name', '').lower() == 'set-cookie' for h in response.get('headers', [])
        )

        # --- Pass 1: Filter out irrelevant entries ---
        if primary_domain:
            host = urlparse(req_url).netloc
            if not host.endswith(primary_domain) and not has_set_cookie:
                continue

        mime_type = response.get('content', {}).get('mimeType', '')
        if is_blocked_mimetype(mime_type) and not has_set_cookie:
            continue

        # --- Pass 2: Trim the data within the remaining entries ---
        trimmed_entry = {
            "startedDateTime": entry.get("startedDateTime"),
            "request": {
                "method": request.get('method'),
                "url": request.get('url'),
                # Keep ALL original request headers. They are essential for context.
                "headers": request.get('headers', []),
                **({"postData": request['postData']} if 'postData' in request else {})
            },
            "response": {
                "status": response.get('status'),
                "statusText": response.get('statusText'),
                "headers": [
                    h for h in response.get('headers', []) 
                    if h.get('name', '').lower() in RESPONSE_HEADER_WHITELIST
                ],
                "content": response.get('content', {})
            }
        }

        # Ensure text exists for content, then truncate if very large
        if "content" in trimmed_entry["response"] and "text" not in trimmed_entry["response"]["content"]:
            trimmed_entry["response"]["content"]["text"] = ""
        if "content" in trimmed_entry["response"] and "text" in trimmed_entry["response"]["content"]:
            trimmed_entry["response"]["content"]["text"] = truncate_text(trimmed_entry["response"]["content"]["text"])

        # Truncate request body text if present
        if "postData" in trimmed_entry["request"] and isinstance(trimmed_entry["request"]["postData"], dict):
            if "text" in trimmed_entry["request"]["postData"]:
                trimmed_entry["request"]["postData"]["text"] = truncate_text(trimmed_entry["request"]["postData"]["text"])

        filtered_entries.append(trimmed_entry)

    print(f"Filtering complete. Kept {len(filtered_entries)} out of {len(har_data['log']['entries'])} original entries.")
    new_har_data['log']['entries'] = filtered_entries
    return new_har_data


if __name__ == '__main__':
    input_har_file = 'runs/session.har' # Using the new unfiltered file
    output_har_file = 'filtered_session_complete.har'

    try:
        with open(input_har_file, 'r', encoding='utf-8') as f:
            har_data = json.load(f)
            
        filtered_data = filter_har_data(har_data)

        with open(output_har_file, 'w', encoding='utf-8') as f:
            json.dump(filtered_data, f, indent=2)
            
        print(f"Successfully created corrected filtered HAR file at: {output_har_file}")

    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_har_file}'")
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON from '{input_har_file}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")