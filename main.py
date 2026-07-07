import os
import re
import json
import time
import pandas as pd
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse, urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager


EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

PHONE_REGEX = (
    r"(\+1|1)?[\s\-.()]?\d{3}[\s\-.()]?\d{3}[\s\-.()]?\d{4}"
    r"|"
    r"(\+92|0092|92|0)?[\s-]?(3\d{2}|21|42|51)[\s-]?\d{3}[\s-]?\d{4}"
)

SOCIAL_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "x.com",
    "twitter.com",
    "pinterest.com"
]

SEARCH_QUERIES_FILE = "search_queries.txt"
BACKUP_FILE = "live_backup.csv"
OUTPUT_FILE = "google_maps_leads_master.csv"

REQUIRE_PHONE_OR_EMAIL = True

OWNER_SEARCH_ENABLED = True
OWNER_WEBSITE_PAGE_LIMIT = 8
OWNER_GOOGLE_RESULT_LIMIT = 5


BAD_OWNER_WORDS = [
    "google", "facebook", "instagram", "linkedin", "twitter", "youtube",
    "contact", "about", "home", "services", "reviews", "rating", "stars",
    "privacy", "terms", "jobs", "companies", "featured", "members",
    "roofing", "company", "contractor", "commercial", "repair",
    "construction", "services", "inc", "llc", "ltd", "corp",
    "houston", "dallas", "texas", "tx", "near", "best",
    "login", "signup", "copyright", "reserved", "results",
    "overview", "people", "also", "ask", "search", "publishing",
    "times", "profile", "yelp", "estimate", "bbb", "bureau",
    "imports", "mission", "partners", "group", "holdings",
    "enterprises", "association", "directory", "magazine"
]


def clean_text(text):
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--lang=en")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    return driver


def read_search_queries():
    possible_files = [
        SEARCH_QUERIES_FILE,
        "search_queries",
        "queries.txt",
        "queries"
    ]

    file_path = None

    for file_name in possible_files:
        if os.path.exists(file_name):
            file_path = file_name
            break

    if not file_path:
        print("Search queries file not found.")
        print("Create search_queries.txt in the same folder.")
        return []

    queries = []

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            query = clean_text(line)

            if query and query not in queries:
                queries.append(query)

    return queries


def request_html(url, timeout=12):
    if not url:
        return ""

    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True
        )

        if response.status_code >= 400:
            return ""

        content_type = response.headers.get("Content-Type", "").lower()

        if content_type and "html" not in content_type:
            return ""

        return response.text

    except Exception:
        return ""


def get_text_safe(driver, selectors):
    for selector in selectors:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            text = clean_text(element.text)

            if text:
                return text

        except Exception:
            pass

    return ""


def get_all_listing_links(driver):
    links = []

    try:
        elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place"]')

        for element in elements:
            href = element.get_attribute("href")

            if href and "/maps/place" in href and href not in links:
                links.append(href)

    except Exception:
        pass

    return links


def scroll_results(driver):
    try:
        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight",
            feed
        )
        time.sleep(2.5)

    except Exception:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.5)


def extract_phone_from_text(text):
    if not text:
        return ""

    match = re.search(PHONE_REGEX, text)

    if match:
        return clean_text(match.group())

    return ""


def extract_rating_and_reviews(driver):
    rating = ""
    review_count = ""

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body_text = ""

    try:
        elements = driver.find_elements(By.CSS_SELECTOR, "span, div, button")
    except Exception:
        elements = []

    combined_texts = []

    if body_text:
        combined_texts.append(body_text)

    for element in elements:
        try:
            text = clean_text(element.text)
            aria = clean_text(element.get_attribute("aria-label") or "")

            if text:
                combined_texts.append(text)

            if aria:
                combined_texts.append(aria)

        except Exception:
            pass

    full_text = "\n".join(combined_texts)

    rating_patterns = [
        r"([0-5]\.\d)\s+stars",
        r"([0-5]\.\d)\s+star",
        r"Rated\s+([0-5]\.\d)",
        r"rating\s+([0-5]\.\d)",
        r"^([0-5]\.\d)$"
    ]

    review_patterns = [
        r"([\d,]+)\s+reviews",
        r"([\d,]+)\s+Google reviews",
        r"\(([\d,]+)\)"
    ]

    for pattern in rating_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE)

        if match:
            rating = clean_text(match.group(1))
            break

    for pattern in review_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)

        if match:
            review_count = clean_text(match.group(1)).replace(",", "")
            break

    return rating, review_count


def extract_email_and_socials_from_website(url):
    emails = set()
    socials = set()

    html = request_html(url)

    if not html:
        return "", ""

    found_emails = re.findall(EMAIL_REGEX, html)

    for email in found_emails:
        emails.add(email)

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_href = urljoin(url, href)

        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0]

            if re.match(EMAIL_REGEX, email):
                emails.add(email)

        lower_href = full_href.lower()

        if any(domain in lower_href for domain in SOCIAL_DOMAINS):
            socials.add(full_href)

    return ", ".join(sorted(emails)), ", ".join(sorted(socials))


def clean_owner_name(name):
    name = clean_text(name)

    name = name.replace("+", " ")
    name = name.replace("Scraped:", "")
    name = re.sub(r"\(.*?\)", " ", name)

    # Hyphen is at the end to avoid regex range error.
    name = re.sub(r"[^a-zA-Z\s.'&-]", " ", name)

    name = clean_text(name)

    titles = [
        "Mr", "Mrs", "Ms", "Miss", "Dr",
        "CEO", "Founder", "Co Founder", "Co-Founder",
        "Owner", "President", "Director", "Principal",
        "Registered Manager", "Manager"
    ]

    for title in titles:
        if name.lower().startswith(title.lower() + " "):
            name = name[len(title):].strip()

    return clean_text(name)


def is_valid_person_name(name, business_name=""):
    name = clean_owner_name(name)

    if not name:
        return False

    if len(name) < 5 or len(name) > 100:
        return False

    lower_name = name.lower()
    lower_business = business_name.lower()

    banned_phrases = [
        "results ai overview",
        "ai overview",
        "people also ask",
        "search results",
        "show results",
        "missing",
        "read more",
        "learn more",
        "view all",
        "google maps",
        "google search",
        "the owner",
        "the founder",
        "owner name",
        "better business bureau",
        "bbb",
        "company profile",
        "business type",
        "headquarters"
    ]

    for phrase in banned_phrases:
        if phrase in lower_name:
            return False

    if lower_business:
        business_words = set(re.sub(r"[^a-z0-9]+", " ", lower_business).split())
        name_words = set(re.sub(r"[^a-z0-9]+", " ", lower_name).split())

        overlap = business_words.intersection(name_words)

        if len(overlap) >= 2:
            return False

    words = lower_name.split()

    if any(word in words for word in BAD_OWNER_WORDS):
        return False

    split_names = re.split(r"\s+and\s+|,\s*|&", name)

    valid_count = 0

    for single_name in split_names:
        single_name = clean_text(single_name)

        if not single_name:
            continue

        parts = single_name.split()

        if len(parts) < 2 or len(parts) > 3:
            continue

        part_ok = True

        for part in parts:
            clean_part = re.sub(r"[^a-zA-Z.'-]", "", part)

            if not clean_part:
                part_ok = False
                break

            if not clean_part[0].isupper():
                part_ok = False
                break

        if part_ok:
            valid_count += 1

    return valid_count >= 1


def extract_owner_from_json_ld(html, business_name=""):
    if not html:
        return "", "", ""

    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            raw_json = script.string

            if not raw_json:
                continue

            data = json.loads(raw_json)
            items = data if isinstance(data, list) else [data]

            expanded_items = []

            for item in items:
                expanded_items.append(item)

                if isinstance(item, dict) and "@graph" in item:
                    graph = item.get("@graph", [])

                    if isinstance(graph, list):
                        expanded_items.extend(graph)

            for item in expanded_items:
                if not isinstance(item, dict):
                    continue

                fields = [
                    "founder",
                    "founders",
                    "owner",
                    "employee",
                    "member",
                    "creator"
                ]

                for field in fields:
                    value = item.get(field)

                    if not value:
                        continue

                    if isinstance(value, str):
                        name = clean_owner_name(value)

                        if is_valid_person_name(name, business_name):
                            return name, "website_json_ld", "high"

                    if isinstance(value, dict):
                        name = clean_owner_name(value.get("name", ""))

                        if is_valid_person_name(name, business_name):
                            return name, "website_json_ld", "high"

                    if isinstance(value, list):
                        for person in value:
                            if isinstance(person, dict):
                                name = clean_owner_name(person.get("name", ""))

                                if is_valid_person_name(name, business_name):
                                    return name, "website_json_ld", "high"

                            elif isinstance(person, str):
                                name = clean_owner_name(person)

                                if is_valid_person_name(name, business_name):
                                    return name, "website_json_ld", "high"

        except Exception:
            pass

    return "", "", ""


def extract_owner_from_google_ai_overview(text, business_name):
    """
    Handles:
    - The owners of EZ Roof and Construction are Alejandro Suarez and Angelica Cuartas.
    - The owner and CEO of Precision Roof Crafters, Inc. is Hisham Rahman.
    - The CEO of Business is Name.
    - Business is owned by Name.
    """
    if not text or not business_name:
        return "", "", ""

    text = clean_text(text)
    text = text.replace("\n", " ")
    text = clean_text(text)

    business_name = business_name.replace("Scraped:", "").strip()
    escaped_business = re.escape(business_name)

    patterns = [
        rf"(?:the\s+)?owners?\s+of\s+{escaped_business}.*?\s+(?:are|is)\s+(.+?)(?:\.|Company Profile|The company's|Would you|Learn more|Read more|$)",

        rf"(?:the\s+)?owner\s+(?:and\s+ceo\s+)?of\s+{escaped_business}.*?\s+(?:is|are)\s+(.+?)(?:\.|Company Profile|The company's|Would you|Learn more|Read more|$)",

        rf"(?:the\s+)?(?:ceo|founder|president|principal)\s+of\s+{escaped_business}.*?\s+(?:is|are)\s+(.+?)(?:\.|Company Profile|The company's|Would you|Learn more|Read more|$)",

        rf"{escaped_business}.*?(?:is\s+owned\s+by|owned\s+by|owners?\s+are|owner\s+is)\s+(.+?)(?:\.|Company Profile|The company's|Would you|Learn more|Read more|$)",

        rf"{escaped_business}.*?(?:registered manager|manager)\s+(?:is|are)?\s*(.+?)(?:\.|Company Profile|The company's|Would you|Learn more|Read more|$)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if not match:
            continue

        owner_text = clean_text(match.group(1))

        owner_text = re.sub(r"\([^)]*\)", " ", owner_text)

        owner_text = re.split(
            r"\s+(?:based in|he has|she has|they have|the company|company's|lead production|engineer|founder|would you|request|estimate|read customer|learn more|also the|with the|headquarters|business type|accreditations|serves as|primary principal)",
            owner_text,
            flags=re.IGNORECASE
        )[0]

        owner_text = clean_owner_name(owner_text)

        names = re.findall(
            r"[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2}",
            owner_text
        )

        valid_names = []

        for name in names:
            name = clean_owner_name(name)

            if is_valid_person_name(name, business_name):
                valid_names.append(name)

        if valid_names:
            final_names = []

            for name in valid_names:
                if name not in final_names:
                    final_names.append(name)

            return " and ".join(final_names), "google_ai_overview", "medium"

    return "", "", ""


def extract_owner_from_text(text, business_name=""):
    if not text:
        return "", "", ""

    text = clean_text(text)

    noise_phrases = [
        "AI Overview",
        "People also ask",
        "Search Results",
        "Related searches",
        "Images",
        "Videos",
        "Forums",
        "Short videos",
        "More results",
        "Sponsored"
    ]

    for phrase in noise_phrases:
        text = text.replace(phrase, " ")

    patterns = [
        r"(?:founder|owner|business owner|co-founder|co founder|ceo|president|principal|director)\s+(?:is|was|named|called)?\s*([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2})",

        r"(?:founded by|owned by|operated by|managed by)\s+([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2}(?:\s+and\s+[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2})?)",

        r"([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2})\s+(?:is|was)?\s*(?:the)?\s*(?:founder|owner|business owner|co-founder|co founder|ceo|president|principal|director)",

        r"founder\s+([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2})\s+(?:began|started|launched|created)",

        r"owned and operated by\s+(?:founder\s+)?([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,2})"
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)

        for match in matches:
            name = clean_owner_name(match)

            if is_valid_person_name(name, business_name):
                return name, "public_text_pattern", "medium"

    return "", "", ""


def get_internal_website_links(base_url, html):
    links = []

    if not base_url or not html:
        return links

    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower().replace("www.", "")

    priority_words = [
        "about",
        "team",
        "staff",
        "leadership",
        "company",
        "our-story",
        "story",
        "contact",
        "owner",
        "founder",
        "management"
    ]

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = clean_text(a.get_text(" ")).lower()
        full_url = urljoin(base_url, href)

        parsed = urlparse(full_url)
        domain = parsed.netloc.lower().replace("www.", "")

        if domain != base_domain:
            continue

        check_value = f"{full_url.lower()} {text}"

        if any(word in check_value for word in priority_words):
            if full_url not in links:
                links.append(full_url)

        if len(links) >= OWNER_WEBSITE_PAGE_LIMIT:
            break

    return links


def find_owner_from_website(website_url, business_name=""):
    if not website_url:
        return "", "", ""

    homepage_html = request_html(website_url)

    if not homepage_html:
        return "", "", ""

    owner, source, confidence = extract_owner_from_json_ld(homepage_html, business_name)

    if owner:
        return owner, source, confidence

    soup = BeautifulSoup(homepage_html, "html.parser")
    homepage_text = soup.get_text(" ")

    owner, source, confidence = extract_owner_from_text(homepage_text, business_name)

    if owner:
        return owner, "website_homepage", confidence

    internal_links = get_internal_website_links(website_url, homepage_html)

    for link in internal_links:
        html = request_html(link)

        if not html:
            continue

        owner, source, confidence = extract_owner_from_json_ld(html, business_name)

        if owner:
            return owner, link, confidence

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ")

        owner, source, confidence = extract_owner_from_text(page_text, business_name)

        if owner:
            return owner, link, "high"

        time.sleep(0.5)

    return "", "", ""


def get_google_result_links(driver, max_links=5):
    links = []

    try:
        anchors = driver.find_elements(By.CSS_SELECTOR, "a")

        for a in anchors:
            href = a.get_attribute("href") or ""

            if not href:
                continue

            if not href.startswith("http"):
                continue

            blocked_domains = [
                "google.com",
                "webcache.googleusercontent.com",
                "accounts.google.com",
                "support.google.com",
                "policies.google.com"
            ]

            if any(domain in href.lower() for domain in blocked_domains):
                continue

            if href not in links:
                links.append(href)

            if len(links) >= max_links:
                break

    except Exception:
        pass

    return links


def extract_owner_from_google_cards(driver, business_name):
    try:
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            "div.g, div[data-sokoban-container], div.MjjYud"
        )

        for card in cards:
            try:
                card_text = clean_text(card.text)

                if not card_text:
                    continue

                lower = card_text.lower()

                if not any(word in lower for word in ["owner", "founder", "owned by", "founded by", "ceo"]):
                    continue

                owner, source, confidence = extract_owner_from_text(card_text, business_name)

                if owner:
                    return owner, "google_result_snippet", "medium"

            except Exception:
                pass

    except Exception:
        pass

    return "", "", ""


def search_owner_google(driver, business_name, address=""):
    if not OWNER_SEARCH_ENABLED:
        return "", "", ""

    if not business_name:
        return "", "", ""

    business_name = business_name.replace("Scraped:", "").strip()

    queries = [
        f'"{business_name}" owner name',
        f'"{business_name}" owner',
        f'"{business_name}" owners',
        f'"{business_name}" founder',
        f'"{business_name}" "owned by"',
        f'"{business_name}" "founded by"',
        f'"{business_name}" CEO',
        f'"{business_name}" about us'
    ]

    if address:
        short_address = address[:70]
        queries.append(f'"{business_name}" "{short_address}" owner')
        queries.append(f'"{business_name}" "{short_address}" founder')

    for query in queries:
        try:
            print(f"Searching owner on Google: {query}")

            google_url = f"https://www.google.com/search?q={quote_plus(query)}"
            driver.get(google_url)

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            time.sleep(5)

            page_text = driver.find_element(By.TAG_NAME, "body").text

            owner, source, confidence = extract_owner_from_google_ai_overview(
                page_text,
                business_name
            )

            if owner:
                return owner, f"{source}: {query}", confidence

            owner, source, confidence = extract_owner_from_google_cards(driver, business_name)

            if owner and is_valid_person_name(owner, business_name):
                return owner, f"{source}: {query}", confidence

            result_links = get_google_result_links(
                driver,
                max_links=OWNER_GOOGLE_RESULT_LIMIT
            )

            for link in result_links:
                html = request_html(link, timeout=12)

                if not html:
                    continue

                owner, source, confidence = extract_owner_from_json_ld(html, business_name)

                if owner and is_valid_person_name(owner, business_name):
                    return owner, link, "high"

                soup = BeautifulSoup(html, "html.parser")
                result_page_text = soup.get_text(" ")

                if not any(
                    word in result_page_text.lower()
                    for word in ["owner", "founder", "owned by", "founded by", "ceo", "president"]
                ):
                    continue

                owner, source, confidence = extract_owner_from_text(
                    result_page_text,
                    business_name
                )

                if owner and is_valid_person_name(owner, business_name):
                    return owner, link, "high"

                time.sleep(0.5)

        except Exception as e:
            print("Owner Google search error:", e)

    return "", "", ""


def find_business_owner_name(driver, data):
    business_name = data.get("name", "")
    address = data.get("address", "")
    website = data.get("website_link", "")
    socials = data.get("social_media_accounts", "")

    owner, source, confidence = find_owner_from_website(website, business_name)

    if owner:
        return owner, source, confidence

    if socials:
        social_links = [link.strip() for link in socials.split(",") if link.strip()]

        for social_link in social_links[:3]:
            html = request_html(social_link, timeout=10)

            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(" ")

            owner, source, confidence = extract_owner_from_text(text, business_name)

            if owner:
                return owner, social_link, "medium"

            time.sleep(0.5)

    owner, source, confidence = search_owner_google(driver, business_name, address)

    if owner:
        return owner, source, confidence

    return "", "", ""


def extract_listing_data(driver):
    wait = WebDriverWait(driver, 20)

    data = {
        "name": "",
        "business_owner_name": "",
        "owner_source": "",
        "owner_confidence": "",
        "contact": "",
        "address": "",
        "social_media_accounts": "",
        "website_available": "No",
        "website_link": "",
        "phone_number": "",
        "email_id": "",
        "google_rating": "",
        "review_count": "",
        "source_query": ""
    }

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
    except Exception:
        pass

    time.sleep(2)

    data["name"] = get_text_safe(driver, ["h1"])

    rating, review_count = extract_rating_and_reviews(driver)

    data["google_rating"] = rating
    data["review_count"] = review_count

    try:
        buttons_and_links = driver.find_elements(By.CSS_SELECTOR, "button, a")
    except Exception:
        buttons_and_links = []

    socials = set()

    for item in buttons_and_links:
        try:
            text = clean_text(item.text)
            aria = clean_text(item.get_attribute("aria-label") or "")
            href = clean_text(item.get_attribute("href") or "")
            combined = clean_text(f"{text} {aria} {href}")

            if "Address:" in aria:
                address = aria.replace("Address:", "")
                data["address"] = clean_text(address)

            if "Phone:" in aria:
                phone = aria.replace("Phone:", "")
                data["phone_number"] = clean_text(phone)
                data["contact"] = data["phone_number"]

            if not data["phone_number"]:
                phone = extract_phone_from_text(combined)

                if phone:
                    data["phone_number"] = phone
                    data["contact"] = phone

            if href and href.startswith("http"):
                domain = urlparse(href).netloc.lower()

                if any(social in domain for social in SOCIAL_DOMAINS):
                    socials.add(href)

                elif (
                    "google.com" not in domain
                    and "gstatic.com" not in domain
                    and "ggpht.com" not in domain
                    and "googleusercontent.com" not in domain
                    and "maps.app.goo.gl" not in domain
                ):
                    if not data["website_link"]:
                        data["website_available"] = "Yes"
                        data["website_link"] = href

        except Exception:
            pass

    if not data["address"]:
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            lines = page_text.split("\n")

            for line in lines:
                line = clean_text(line)

                if len(line) > 15:
                    address_words = [
                        "street", "road", "rd", "suite", "tx",
                        "karachi", "houston", "dallas", "austin",
                        "san antonio", "fort worth", "el paso",
                        "arlington", "plano"
                    ]

                    if any(word in line.lower() for word in address_words):
                        data["address"] = line
                        break

        except Exception:
            pass

    if data["website_link"]:
        email, website_socials = extract_email_and_socials_from_website(
            data["website_link"]
        )

        if email:
            data["email_id"] = email

        if website_socials:
            for link in website_socials.split(", "):
                if link:
                    socials.add(link)

    data["social_media_accounts"] = ", ".join(sorted(socials))

    owner_name, owner_source, owner_confidence = find_business_owner_name(
        driver,
        data
    )

    data["business_owner_name"] = owner_name
    data["owner_source"] = owner_source
    data["owner_confidence"] = owner_confidence

    return data


def normalize_phone(phone):
    phone = clean_text(phone).lower()
    phone = re.sub(r"[^0-9+]", "", phone)
    return phone


def normalize_website(website):
    website = clean_text(website).lower()
    website = website.replace("https://", "")
    website = website.replace("http://", "")
    website = website.replace("www.", "")
    website = website.rstrip("/")
    return website


def normalize_name_address(name, address):
    value = f"{name} {address}".lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = clean_text(value)
    return value


def is_duplicate(item, seen_names_addresses, seen_phones, seen_websites):
    name = item.get("name", "")
    address = item.get("address", "")
    phone = normalize_phone(item.get("phone_number", ""))
    website = normalize_website(item.get("website_link", ""))
    name_address = normalize_name_address(name, address)

    if phone and phone in seen_phones:
        return True

    if website and website in seen_websites:
        return True

    if name_address and name_address in seen_names_addresses:
        return True

    return False


def mark_seen(item, seen_names_addresses, seen_phones, seen_websites):
    name = item.get("name", "")
    address = item.get("address", "")
    phone = normalize_phone(item.get("phone_number", ""))
    website = normalize_website(item.get("website_link", ""))
    name_address = normalize_name_address(name, address)

    if phone:
        seen_phones.add(phone)

    if website:
        seen_websites.add(website)

    if name_address:
        seen_names_addresses.add(name_address)


def save_csv(scraped_data, output_file):
    columns = [
        "name",
        "business_owner_name",
        "owner_source",
        "owner_confidence",
        "contact",
        "address",
        "social_media_accounts",
        "website_available",
        "website_link",
        "phone_number",
        "email_id",
        "google_rating",
        "review_count",
        "source_query"
    ]

    df = pd.DataFrame(scraped_data)
    df = df.reindex(columns=columns)

    if not df.empty:
        df = df.drop_duplicates(
            subset=["phone_number", "website_link", "name", "address"],
            keep="first"
        )

    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    return len(df)


def scrape_query(
    driver,
    query,
    required_count,
    scraped_data,
    processed_links,
    seen_names_addresses,
    seen_phones,
    seen_websites
):
    print("\n====================================")
    print(f"Searching query: {query}")
    print("====================================")

    encoded_query = quote_plus(query)
    search_url = f"https://www.google.com/maps/search/{encoded_query}"

    driver.get(search_url)

    wait = WebDriverWait(driver, 40)

    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[role="feed"], a[href*="/maps/place"]')
            )
        )
        print("Google Maps results loaded.")

    except Exception:
        print("Google Maps results did not load.")
        print("Page title:", driver.title)
        print("Current URL:", driver.current_url)
        return

    time.sleep(4)

    no_new_rounds = 0

    while len(scraped_data) < required_count:
        listing_links = get_all_listing_links(driver)

        new_links = [
            link for link in listing_links
            if link not in processed_links
        ]

        if not new_links:
            no_new_rounds += 1
            scroll_results(driver)

            if no_new_rounds >= 6:
                print(f"No more new listings found for query: {query}")
                break

            continue

        no_new_rounds = 0

        for link in new_links:
            if len(scraped_data) >= required_count:
                break

            processed_links.add(link)

            try:
                driver.execute_script("window.open(arguments[0], '_blank');", link)
                driver.switch_to.window(driver.window_handles[-1])

                item = extract_listing_data(driver)
                item["source_query"] = query

                has_contact = bool(item["phone_number"] or item["email_id"])

                if not item["name"]:
                    print("Skipped: no name found.")

                elif REQUIRE_PHONE_OR_EMAIL and not has_contact:
                    print(f"Skipped no phone/email: {item['name']}")

                elif is_duplicate(
                    item,
                    seen_names_addresses,
                    seen_phones,
                    seen_websites
                ):
                    print(f"Duplicate skipped: {item['name']}")

                else:
                    scraped_data.append(item)
                    mark_seen(
                        item,
                        seen_names_addresses,
                        seen_phones,
                        seen_websites
                    )

                    owner_print = (
                        item["business_owner_name"]
                        if item["business_owner_name"]
                        else "Owner not found"
                    )

                    print(
                        f"[{len(scraped_data)}] Scraped: {item['name']} | "
                        f"Owner: {owner_print} | "
                        f"Rating: {item['google_rating']} | "
                        f"Reviews: {item['review_count']}"
                    )

                    save_csv(scraped_data, BACKUP_FILE)

                try:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass

                time.sleep(1)

            except Exception as e:
                print("Error scraping listing:", e)

                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass

        scroll_results(driver)


def main():
    try:
        required_count = int(input("How many leads do you want? "))
    except ValueError:
        print("Please enter a valid number.")
        return

    queries = read_search_queries()

    if not queries:
        return

    print(f"\nTotal search queries found: {len(queries)}")
    print("Bot will keep moving to next query until required leads are completed.\n")

    driver = setup_driver()

    scraped_data = []
    processed_links = set()
    seen_names_addresses = set()
    seen_phones = set()
    seen_websites = set()

    try:
        for query in queries:
            if len(scraped_data) >= required_count:
                break

            scrape_query(
                driver=driver,
                query=query,
                required_count=required_count,
                scraped_data=scraped_data,
                processed_links=processed_links,
                seen_names_addresses=seen_names_addresses,
                seen_phones=seen_phones,
                seen_websites=seen_websites
            )

        final_count = save_csv(scraped_data, OUTPUT_FILE)

        print("\nScraping completed.")
        print(f"Required leads: {required_count}")
        print(f"Total leads saved: {final_count}")
        print(f"CSV file saved as: {OUTPUT_FILE}")

        if final_count < required_count:
            print("\nNote:")
            print("Bot searched all queries but could not reach the exact required count.")
            print("Add more search queries in search_queries.txt and run again.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()