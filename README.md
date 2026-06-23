# Google Map Scrapper

A Python Selenium-based scraper for collecting public business data from Google Maps search results.

This project opens each Google Maps listing in a new browser tab, extracts available business information, avoids duplicate records, and saves the final data into a CSV file.

## Features

* Scrape business name
* Scrape contact number
* Scrape address
* Scrape website link
* Check whether website is available
* Extract public email address from website if available
* Extract social media links if available
* Avoid duplicate records
* Open each listing in a new browser tab
* Save scraped data in CSV format

## Data Fields

The CSV output includes the following columns:

```text
name
contact
address
social_media_accounts
website_available
website_link
phone_number
email_id
```

## Requirements

Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Required Packages

```text
selenium
pandas
requests
beautifulsoup4
webdriver-manager
```

## Usage

Run the scraper:

```bash
python main.py
```

The script will ask:

```text
How many records do you want?
```

Then it will ask for a Google Maps search query:

```text
Enter search query, for example 'Salon & Spa in Karachi':
```

Example query:

```text
Salon & Spa in Karachi
```

## Output

The scraper creates a CSV file:

```text
karachi_salon_spa_data.csv
```

## Example Output

```csv
name,contact,address,social_media_accounts,website_available,website_link,phone_number,email_id
Example Salon,+923001234567,"Karachi, Pakistan","https://facebook.com/example","Yes","https://example.com","+923001234567","info@example.com"
```

## Notes

Google Maps may sometimes show a captcha, consent page, or sign-in page. If that happens, clear it manually in the browser and run the script again.

Email addresses are not always available on Google Maps. The script checks the business website and extracts public emails only when available.

## Disclaimer

This tool is for educational purposes only. Scrape only publicly available information and use the tool responsibly. Make sure your usage follows the terms of service of the websites you access.
