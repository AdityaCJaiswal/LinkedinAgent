import os
import json
import re
import subprocess
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Load Environment Variables
load_dotenv()

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials. Check your .env file.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Gemini Client
client = genai.Client()

# 1. DEFINE THE STRICT SCHEMA
class TailoredResume(BaseModel):
    summary_placeholder: str = Field(description="A 2-3 line profile summary tailored to the job description.")
    streamstudio_bullets: str = Field(description="Exactly 3 valid LaTeX bullets for StreamStudio, using the \\resumeItem{...} macro.")
    redline_bullets: str = Field(description="Exactly 3 valid LaTeX bullets for Redline AI, using the \\resumeItem{...} macro.")
    amazon_ml_bullets: str = Field(description="Exactly 3 valid LaTeX bullets for Amazon ML, using the \\resumeItem{...} macro.")
    adaptive_learn_bullets: str = Field(description="Exactly 3 valid LaTeX bullets for Adaptive Learn, using the \\resumeItem{...} macro.")
    colosseum_bullets: str = Field(description="Exactly 3 valid LaTeX bullets for Colosseum Experience, using the \\resumeItem{...} macro.")

def fetch_pending_job():
    try:
        response = supabase.table("fresher_jobs").select("*").eq("status", "pending_review").limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Network or Database Error: {e}")
        print("Supabase might be down or unreachable. Try again in 5 minutes.")
        return None
    
def generate_tailored_json(job_title, job_company, job_description):
    original_context = """
    Original Summary: AWS & OCI Certified Full Stack Developer specializing in the MERN stack, Python, and Cloud-Native architectures. Experienced in building Agentic AI systems (RAG/LLMs) and deploying scalable, containerized applications using Docker.
    Original StreamStudio: Engineered high-performance broadcast tool achieving sub-200ms latency. Custom MJPEG pipeline bypassing HLS. Hybrid video engine (FFmpeg/OpenCV). React dashboard with MongoDB.
    Original Redline AI: Offline RAG system for legal risk detection. Hybrid engine (keyword + Local LLM). FAISS vector search optimized 40%. Docker deployment.
    Original Amazon ML: Multimodal ML pipeline. CNNs and OCR for visual data. Optimized LightGBM models. Large-scale dataset processing.
    Original Adaptive Learn: AI educational platform. YouTube Data API integration. Predictive modeling (25% engagement increase). Supabase real-time DB & OAuth.
    Original Colosseum: Led 5 developers for event platform. Designed game assets (Aseprite). Managed logistics (99.9% uptime).
    """

    prompt = fr"""
    You are an elite technical recruiter and resume writer. 
    I am applying for a {job_title} role at {job_company}.
    
    Analyze the Job Description below. Then, rewrite my original resume bullet points to heavily emphasize the specific technologies, skills, and keywords the employer is looking for.
    
    CRITICAL RULES:
    1. DO NOT hallucinate skills or metrics I do not have. Only reframe my existing accomplishments.
    2. You MUST use my custom LaTeX macro \resumeItem{{Your text here}} for EVERY bullet. Do NOT use the standard \item. 
    3. Output exactly 3 \resumeItem{{...}} blocks for each project/experience field.
    4. Do not include any markdown formatting or \begin{{itemize}} blocks in the fields. Just the raw \resumeItem{{...}} strings.
    5. VERY IMPORTANT: You must escape LaTeX special characters. If you use a percent sign, write it as \%. If you use an ampersand, write it as \&.
    
    Job Description:
    {job_description}
    
    My Original Accomplishments:
    {original_context}
    """

    print(f"Calling Gemini to analyze JD and tailor resume for {job_company}...")
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TailoredResume,
            temperature=0.1, # Lowered for more predictable output
        ),
    )
    
    return json.loads(response.text)

def sanitize_latex(text):
    """
    Crucial Step: Catches unescaped LaTeX characters that the LLM might miss, 
    preventing compilation crashes.
    """
    if not text:
        return ""
    
    # Escape unescaped %, &, and $
    text = re.sub(r'(?<!\\)%', r'\%', text)
    text = re.sub(r'(?<!\\)&', r'\&', text)
    text = re.sub(r'(?<!\\)\$', r'\$', text)
    return text

def compile_latex(job_id, tailored_data):
    with open("base_resume.tex", "r") as file:
        template = file.read()

    # Inject AND Sanitize the AI-generated JSON into the placeholders
    template = template.replace("%%%SUMMARY_PLACEHOLDER%%%", sanitize_latex(tailored_data['summary_placeholder']))
    template = template.replace("%%%STREAMSTUDIO_BULLETS%%%", sanitize_latex(tailored_data['streamstudio_bullets']))
    template = template.replace("%%%REDLINE_BULLETS%%%", sanitize_latex(tailored_data['redline_bullets']))
    template = template.replace("%%%AMAZON_ML_BULLETS%%%", sanitize_latex(tailored_data['amazon_ml_bullets']))
    template = template.replace("%%%ADAPTIVE_LEARN_BULLETS%%%", sanitize_latex(tailored_data['adaptive_learn_bullets']))
    template = template.replace("%%%COLOSSEUM_BULLETS%%%", sanitize_latex(tailored_data['colosseum_bullets']))

    temp_filename = f"resume_{job_id}.tex"
    with open(temp_filename, "w") as file:
        file.write(template)

    print(f"Compiling PDF for job {job_id}...")
    try:
        # Run pdflatex. 
        # Note: If pdflatex fails, it usually writes an error to the .log file before exiting.
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", temp_filename], 
            check=True, 
            capture_output=True, # Capture output to prevent spamming terminal unless there's an error
            text=True
        )
        print(f"Success! PDF generated: resume_{job_id}.pdf")
        
        # Cleanup LaTeX junk files
        for ext in [".aux", ".log", ".out"]:
            try:
                os.remove(f"resume_{job_id}{ext}")
            except FileNotFoundError:
                pass
                
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[!] FAILED to compile LaTeX for job {job_id}.")
        print("[!] LaTeX Compiler Output (Look for the '!' character indicating the error):")
        
        # This will print the actual LaTeX error from the console output so you can debug it
        lines = e.stdout.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('!'):
                print(f"  --> {line}")
                # Print a few surrounding lines for context
                for j in range(max(0, i-2), min(len(lines), i+3)):
                    print(f"      {lines[j]}")
                break
                
        return False

def main():
    job = fetch_pending_job()
    if not job:
         print("No pending jobs found in Supabase.")
         return

    print(f"Processing target: {job['title']} at {job['company']}")
    
    tailored_data = generate_tailored_json(job['title'], job['company'], job['job_description'])
    
    success = compile_latex(job['id'], tailored_data)

    if success:
         supabase.table("fresher_jobs").update({"status": "tailored"}).eq("id", job['id']).execute()
         print("Supabase status updated to 'tailored'.")

if __name__ == "__main__":
    main()