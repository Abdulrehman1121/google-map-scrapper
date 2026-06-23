import re
import time
import pandas as pd
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager


EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
PHONE_REGEX = r"(\+92|0092|92|0)?[\s-]?(3\d{2}|21|42|51)[\s-]?\d{3}[\s-]?\d{4}"

SOCIAL_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "x.com",
    "twitter.com"
]


def clean_text(text):
    if not text:
        return ""
    return " ".join(text.split()).strip()


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

    elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place"]')

    for element in elements:
        try:
            href = element.get_attribute("href")
            if href and "/maps/place" in href and href not in links:
                links.append(href)
        except Exception:
            pass

    return links


def scroll_results(driver):
    try:
        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feed)
        time.sleep(2)
    except Exception:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)


def extract_email_and_socials_from_website(url):
    emails = set()
    socials = set()

    if not url:
        return "", ""

    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=12)
        html = response.text

        found_emails = re.findall(EMAIL_REGEX, html)
        for email in found_emails:
            emails.add(email)

        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0]
                if re.match(EMAIL_REGEX, email):
                    emails.add(email)

            lower_href = href.lower()
            if any(domain in lower_href for domain in SOCIAL_DOMAINS):
                socials.add(href)

    except Exception:
        pass

    return ", ".join(sorted(emails)), ", ".join(sorted(socials))


def extract_listing_data(driver):
    wait = WebDriverWait(driver, 20)

    data = {
        "name": "",
        "contact": "",
        "address": "",
        "social_media_accounts": "",
        "website_available": "No",
        "website_link": "",
        "phone_number": "",
        "email_id": ""
    }

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
    except Exception:
        pass

    time.sleep(2)

    data["name"] = get_text_safe(driver, ["h1"])

    buttons_and_links = driver.find_elements(By.CSS_SELECTOR, "button, a")

    socials = set()

    for item in buttons_and_links:
        try:
            text = clean_text(item.text)
            aria = item.get_attribute("aria-label") or ""
            href = item.get_attribute("href") or ""

            combined = f"{text} {aria} {href}"
            combined_clean = clean_text(combined)

            # Address
            if "Address:" in aria:
                address = aria.replace("Address:", "")
                data["address"] = clean_text(address)

            # Phone
            if "Phone:" in aria:
                phone = aria.replace("Phone:", "")
                data["phone_number"] = clean_text(phone)
                data["contact"] = data["phone_number"]

            if not data["phone_number"]:
                phone_match = re.search(PHONE_REGEX, combined_clean)
                if phone_match:
                    data["phone_number"] = clean_text(phone_match.group())
                    data["contact"] = data["phone_number"]

            # Website / social links
            if href and href.startswith("http"):
                domain = urlparse(href).netloc.lower()

                if any(social in domain for social in SOCIAL_DOMAINS):
                    socials.add(href)

                elif (
                    "google.com" not in domain
                    and "gstatic.com" not in domain
                    and "ggpht.com" not in domain
                    and "googleusercontent.com" not in domain
                ):
                    if not data["website_link"]:
                        data["website_available"] = "Yes"
                        data["website_link"] = href

        except Exception:
            pass

    # Backup address extraction from page text
    if not data["address"]:
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            lines = page_text.split("\n")

            for line in lines:
                line = clean_text(line)
                if "Karachi" in line and len(line) > 15:
                    data["address"] = line
                    break
        except Exception:
            pass

    # Visit website for email and social links
    if data["website_link"]:
        email, website_socials = extract_email_and_socials_from_website(data["website_link"])

        if email:
            data["email_id"] = email

        if website_socials:
            for link in website_socials.split(", "):
                if link:
                    socials.add(link)

    data["social_media_accounts"] = ", ".join(sorted(socials))

    return data


def is_duplicate(item, seen_names, seen_phones, seen_websites):
    name = item.get("name", "").lower().strip()
    phone = item.get("phone_number", "").strip()
    website = item.get("website_link", "").strip()

    if name and name in seen_names:
        return True

    if phone and phone in seen_phones:
        return True

    if website and website in seen_websites:
        return True

    return False


def mark_seen(item, seen_names, seen_phones, seen_websites):
    name = item.get("name", "").lower().strip()
    phone = item.get("phone_number", "").strip()
    website = item.get("website_link", "").strip()

    if name:
        seen_names.add(name)

    if phone:
        seen_phones.add(phone)

    if website:
        seen_websites.add(website)


def main():
    required_count = int(input("How many records do you want? "))

    query = input("Enter search query, for example 'Salon & Spa in Karachi': ").strip()

    if not query:
        query = "Salon & Spa in Karachi"

    driver = setup_driver()

    scraped_data = []
    seen_names = set()
    seen_phones = set()
    seen_websites = set()
    processed_links = set()

    try:
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

                if no_new_rounds >= 5:
                    print("No more new listings found.")
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

                    # Require at least name
                    if not item["name"]:
                        print("Skipped: no name found.")
                    elif is_duplicate(item, seen_names, seen_phones, seen_websites):
                        print(f"Duplicate skipped: {item['name']}")
                    else:
                        scraped_data.append(item)
                        mark_seen(item, seen_names, seen_phones, seen_websites)

                        print(f"[{len(scraped_data)}] Scraped: {item['name']}")

                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
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

        output_file = "karachi_salon_spa_data.csv"

        df = pd.DataFrame(scraped_data)

        columns = [
            "name",
            "contact",
            "address",
            "social_media_accounts",
            "website_available",
            "website_link",
            "phone_number",
            "email_id"
        ]

        df = df.reindex(columns=columns)
        df.to_csv(output_file, index=False, encoding="utf-8-sig")

        print("\nScraping completed.")
        print(f"Total records saved: {len(scraped_data)}")
        print(f"CSV file saved as: {output_file}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()