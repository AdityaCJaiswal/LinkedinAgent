import os
from dotenv import load_dotenv
from apify_client import ApifyClient
from supabase import create_client, Client

# Load environment variables from the .env file
load_dotenv()

# 1. Initialize Clients 
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Safety Check: Stop the script immediately if keys are still missing
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials. Check your .env file.")

apify = ApifyClient(APIFY_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def run_job_scraper():
    print("Initiating Apify Scraper...")
    
    # Configure the Apify Actor (Find a standard LinkedIn scraper on their store)
    # Target keywords: "Backend Developer Fresher", "Software Engineer Intern", "AI Engineer 0 years"
    run_input = {
        "searchTerms": ["Software Engineer Fresher", "Backend Intern"],
        "location": "India", # Or remote
        "limit": 30 # Keep it small for testing
    }

    # Replace with the actual Actor ID from Apify
    run = apify.actor("JkfTWxtpgfvcRQn3p").call(run_input=run_input)
    
    print("Scraping complete. Processing data...")
    return apify.dataset(run["defaultDatasetId"]).iterate_items()

def process_and_store_jobs(jobs_data):
    inserted_count = 0
    
    for job in jobs_data:
        # 1. Extract using the EXACT keys from your JSON
        title = job.get("job_title", "")
        company = job.get("company_name", "Unknown")
        location = job.get("location", "Remote")
        description = job.get("job_description", "")
        job_url = job.get("job_url", "")
        
        # Lowercase for robust filtering
        desc_lower = description.lower()
        title_lower = title.lower()

        # 2. THE RUTHLESS FILTER
        
        # A. Filter by Title: Kill anything above junior/intern level instantly
        senior_keywords = ["senior", "lead", "manager", "director", "staff", "principal", "head"]
        if any(keyword in title_lower for keyword in senior_keywords):
            continue 

        # B. Filter by Experience: Catch absurd entry-level requirements
        experience_blockers = [
            "3+ years", "4+ years", "5+ years", 
            "minimum 3 years", "minimum 2 years",
            "3 years of experience"
        ]
        if any(blocker in desc_lower for blocker in experience_blockers):
            continue
            
        # C. Filter by Location/Clearance (Optional but recommended for US-heavy scrapers)
        if "security clearance" in desc_lower or "us citizen" in desc_lower:
            continue

        # 3. Prepare Payload for Supabase
        job_payload = {
            "title": title,
            "company": company,
            "location": location,
            "job_description": description,
            "job_url": job_url
        }

        try:
            # Insert into Supabase
            supabase.table("fresher_jobs").insert(job_payload).execute()
            inserted_count += 1
        except Exception as e:
            # Likely a duplicate job_url constraint violation. Ignore and move on.
            pass 

    print(f"Pipeline execution finished. Successfully stored {inserted_count} clean, targeted jobs.")
if __name__ == "__main__":
    raw_jobs = run_job_scraper()
    process_and_store_jobs(raw_jobs)