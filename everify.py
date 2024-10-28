import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import time
import random
import os

# URL and headers setup
url = "https://www.e-verify.gov/views/ajax"
headers = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# Data structure to hold results
data = {
    "Primary Industry Type": [],
    "Employer": [],
    "Doing Business As": [],
    "Workforce Size": [],
    "Number of Hiring Sites": [],
    "Hiring Site Locations (by state)": []
}

# Path to the CSV file
output_csv = "company_data.csv"

# Function to parse the HTML content in the response
def parse_html_table(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table", {"class": "views-table"})  # Find the table with data
    if not table:
        print("No table found in the response.")
        return

    rows = table.find_all("tr")[1:]  # Skip the header row
    for row in rows:
        cols = row.find_all("td")
        data["Primary Industry Type"].append(cols[0].text.strip())
        data["Employer"].append(cols[1].text.strip())
        data["Doing Business As"].append(cols[2].text.strip())
        data["Workforce Size"].append(cols[3].text.strip())
        data["Number of Hiring Sites"].append(cols[4].text.strip())
        data["Hiring Site Locations (by state)"].append(cols[5].text.strip())

# Function to extract total entries from the footer
def get_total_entries(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    footer = soup.find("div", class_="view-footer")
    if footer:
        match = re.search(r'of (\d+) entries', footer.text)
        if match:
            return int(match.group(1))
    return None

# Function to handle requests with retry logic
def fetch_with_retry(url, headers, params, max_retries=3):
    retry_count = 0
    while retry_count < max_retries:
        response = requests.get(url, headers=headers, params=params)
        
        # If the request is successful
        if response.status_code == 200:
            return response
        
        # If blocked or rate-limited, wait and retry
        elif response.status_code in [429, 403]:
            print(f"Blocked or rate-limited (status {response.status_code}). Waiting 5 minutes before retrying...")
            time.sleep(5 * 60)  # Wait for 5 minutes
            retry_count += 1
        else:
            print(f"Unexpected status code {response.status_code}. Retrying...")
            time.sleep(random.uniform(5, 10))  # Short random wait before retrying
            retry_count += 1
    
    # If all retries fail, return None
    print("Max retries reached. Skipping this request.")
    return None

# Function to save data in chunks
def save_to_csv(data, filename):
    df = pd.DataFrame(data)
    if not os.path.isfile(filename):
        df.to_csv(filename, index=False, mode='w')  # Write header if file does not exist
    else:
        df.to_csv(filename, index=False, mode='a', header=False)  # Append without writing the header
    print(f"Data appended to {filename}")

    # Clear data from memory after saving
    for key in data.keys():
        data[key].clear()

# Loop through each state ID
state_ids = list(range(1, 57))  # State IDs from 1 to 56
items_per_page = 10  # You can increase this if the server allows
pages_processed = 0  # Counter to track processed pages

for state_id in state_ids:
    # Fetch the first page to get the total entry count
    params = {
        "status": 1,
        "items_per_page": items_per_page,
        "_wrapper_format": "drupal_ajax",
        "view_name": "participating_employers",
        "view_display_id": "page_1",
        "_drupal_ajax": 1,
        "page": 1,
        "hiringstates[]": state_id
    }
    
    response = fetch_with_retry(url, headers, params)
    if response and response.status_code == 200:
        try:
            json_response = response.json()
            
            # Locate the dictionary containing the HTML with `command` set to 'insert'
            html_content = next(
                (item["data"] for item in json_response if item.get("command") == "insert" and "data" in item), 
                None
            )
            
            if html_content:
                # Get the total number of entries
                total_entries = get_total_entries(html_content)
                if total_entries:
                    max_pages = (total_entries // items_per_page) + (total_entries % items_per_page > 0)
                    print(f"Total entries for state {state_id}: {total_entries} (Total pages: {max_pages})")
                else:
                    print(f"Total entries not found for state {state_id}, defaulting to 5 pages")
                    max_pages = 5  # Default for testing if total not found

                # Parse the first page
                parse_html_table(html_content)
                print(f"Fetched and parsed state {state_id}, page 1")
                pages_processed += 1

                # Loop through the rest of the pages
                for page in range(2, max_pages + 1):
                    params["page"] = page
                    response = fetch_with_retry(url, headers, params)

                    if response and response.status_code == 200:
                        try:
                            json_response = response.json()
                            html_content = next(
                                (item["data"] for item in json_response if item.get("command") == "insert" and "data" in item), 
                                None
                            )
                            
                            if html_content:
                                parse_html_table(html_content)
                                print(f"Fetched and parsed state {state_id}, page {page}")
                                pages_processed += 1
                            else:
                                print(f"No HTML content found for parsing on state {state_id}, page {page}")
                                break
                        except (KeyError, IndexError, ValueError, TypeError) as e:
                            print(f"Error parsing JSON or HTML on state {state_id}, page {page}: {e}")
                            break
                    else:
                        print(f"Failed to fetch state {state_id}, page {page}")
                        break

                    # Save data to CSV every 50 pages
                    if pages_processed >= 50:
                        save_to_csv(data, output_csv)
                        pages_processed = 0  # Reset counter

                    # Random delay between 2 and 5 seconds
                    time.sleep(random.uniform(2, 5))
            else:
                print(f"No HTML content found for state {state_id} on page 1")
        except (KeyError, IndexError, ValueError, TypeError) as e:
            print(f"Error parsing JSON or HTML on state {state_id}, page 1: {e}")
    else:
        print(f"Failed to fetch state {state_id}, page 1")
    
    # Random delay between 5 and 10 seconds before moving to the next state
    time.sleep(random.uniform(5, 10))

# Save any remaining data to CSV after the loop
if any(data[key] for key in data.keys()):
    save_to_csv(data, output_csv)

