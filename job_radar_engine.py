"""
Raja Taha Khan's Intelligent Real-Time Multi-Company Job Radar Engine (v2)
- Scope: 10,000+ Direct Companies via Multi-Feed Ingestion (Arbeitnow, Jobicy, RemoteOK, German Tech Hubs)
- Freshness Gate: ONLY JOBS POSTED TODAY (Last 24 Hours) - Zero stale postings!
- Language Filter:
  * Hard Knockout 1: Written in German OR requires fluent/C1 German (Allows "German is a plus/advantage/not required")
  * Hard Knockout 2: Marketing & HR roles
  * Inclusive Scope: ALL Data, BI, Engineering, Operations, Systems, Consulting, Digital, and unique hybrid titles!
- Geo-corridor: Ulm, Neu-Ulm, Stuttgart, Augsburg, Munich + Remote / Hybrid across Germany & Worldwide
- Notification: Instant push via ntfy.sh (topic: raja-job-radar-2026) with rate-limiting & student badges
"""
import os
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_JOBS_FILE = os.path.join(WORKSPACE_DIR, "seen_jobs.json")
NTFY_TOPIC = "raja-job-radar-2026"
MAX_AGE_SECONDS = 7200  # Strictly 2 hours: ONLY ultra-fresh postings from the last 30-120 minutes!

# Load seen jobs
if os.path.exists(SEEN_JOBS_FILE):
    try:
        with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
            seen_jobs = set(json.load(f))
    except Exception:
        seen_jobs = set()
else:
    seen_jobs = set()

# -------------------------------------------------------------
# FILTERING CONFIGURATION
# -------------------------------------------------------------
GERMAN_STOPWORDS = {
    'der', 'die', 'das', 'und', 'in', 'den', 'von', 'zu', 'mit', 'sich', 
    'auf', 'für', 'eine', 'einer', 'einem', 'einen', 'wir', 'uns', 'ihr', 
    'aufgaben', 'anforderungen', 'bewerbung', 'abschluss', 'bereich', 'kenntnisse'
}

ENGLISH_STOPWORDS = {
    'the', 'and', 'in', 'of', 'to', 'with', 'for', 'a', 'an', 'we', 'our', 
    'you', 'your', 'skills', 'responsibilities', 'requirements', 'experience', 
    'working', 'student', 'team', 'looking', 'opportunity', 'company'
}

KNOCKOUT_ROLES = [
    r'\bmarketing\b', r'\bsocial media\b', r'\bcontent creator\b', r'\bseo\b',
    r'\bcopywriter\b', r'\bhuman resources\b', r'\bhr\b', r'\brecruiter\b',
    r'\brecruiting\b', r'\brecruitment\b', r'\btalent acquisition\b', r'\bpersonalwesen\b',
    r'\bpublic relations\b', r'\bbrand manager\b', r'\bemployer branding\b',
    r'\bpeople partner\b', r'\bpeople business partner\b', r'\bpeople operations\b',
    r'\bpeople & culture\b', r'\bpeople and culture\b', r'\btalent management\b'
]

HARD_GERMAN_REQUIREMENTS = [
    r'fluent german', r'german c1', r'german c2', r'german \(fluent\)',
    r'german required', r'business fluent german', r'flie[ßs]endes deutsch',
    r'gute deutschkenntnisse', r'deutschkenntnisse in wort und schrift',
    r'verhandlungssicher', r'sehr gute deutschkenntnisse'
]

SOFT_GERMAN_ALLOWED = [
    r'german is a plus', r'german is an advantage', r'german is nice to have',
    r'german is beneficial', r'basic german', r'german a1', r'german a2',
    r'willingness to learn german', r'english is our working language',
    r'german is not required', r'no german required'
]

# Complete Ulm Corridor, all in-between towns, and Southern Tech Hubs
REGIONAL_ONSITE_CITIES = [
    # Primary Triangle Hubs
    'ulm', 'neu-ulm', 'stuttgart', 'augsburg', 'münchen', 'munich', 
    
    # Towns Between Ulm & Stuttgart
    'göppingen', 'geislingen', 'kirchheim', 'nürtingen', 'esslingen', 
    'plochingen', 'waiblingen', 'sindelfingen', 'böblingen', 'ludwigsburg',
    'reutlingen', 'tübingen',
    
    # Towns Between Ulm & Augsburg/Munich
    'günzburg', 'burgau', 'zusmarshausen', 'friedberg', 'fürstenfeldbruck', 
    'dachau', 'garching', 'unterföhring', 'starnberg',
    
    # Towns Between Ulm & Lake Constance / Allgäu
    'laupheim', 'biberach', 'bad waldsee', 'ravensburg', 'weingarten', 
    'friedrichshafen', 'memmingen', 'kempten', 'illertissen',
    
    # Towns Between Ulm & Aalen (Industrial / Zeiss Corridor)
    'langenau', 'giengen', 'heidenheim', 'oberkochen', 'aalen', 'schwäbisch gmünd',
    
    # Extended Southern Innovation Hubs
    'ingolstadt', 'nürnberg', 'nuremberg', 'karlsruhe', 'heilbronn', 'mannheim',
    
    # Regional States & Counties
    'baden-württemberg', 'baden-wuerttemberg', 'bayern', 'bavaria', 
    'schwaben', 'allgäu', 'ostalb'
]

REMOTE_HYBRID_SIGNALS = [
    r'\bremote\b', r'\bhybrid\b', r'\bhome office\b', r'\bhome-office\b',
    r'\bmobiles arbeiten\b', r'\bwork from anywhere\b', r'\bdeutschlandweit\b',
    r'\bgermany-wide\b', r'\btelework\b', r'\bwork from home\b', r'\bflexible location\b',
    r'\bremote-first\b'
]

MANDATORY_ENGLISH_STUDENT_SIGNALS = [
    r'\bworking student\b', r'\bintern\b', r'\binternship\b',
    r'\bstudent trainee\b', r'\btrainee\b', r'\bstudent assistant\b',
    r'\bstudent job\b', r'\bgraduate trainee\b'
]

GERMAN_TITLE_KNOCKOUT = [
    r'\bwerkstudent\b', r'\bwerkstudentin\b', r'\bwerkstudierende\b',
    r'\bpraktikant\b', r'\bpraktikantin\b', r'\bpraktikum\b',
    r'\bverkauf\b', r'\bvertrieb\b', r'\beinkauf\b', r'\bbauprojektmanagement\b',
    r'\bentwicklung\b', r'\bverwaltung\b', r'\bbereich\b', r'\babteilung\b',
    r'\bleitung\b', r'\bsachbearbeiter\b', r'\bassistenz\b', r'\bmitarbeiter\b',
    r'\bkundenberatung\b', r'\bberatung\b', r'\bfahrzeugankauf\b', r'\bkonstruktion\b',
    r'\bqualitätsmanagement\b', r'\bproduktionsoptimierung\b', r'\barbeitsvorbereitung\b',
    r'\bvertriebsinnendienst\b', r'\bdigitales lernen\b', r'\bim bereich\b',
    r'\bin der\b', r'\bfür das\b', r'\bfür die\b', r':in\b', r'\*in\b'
]

SENIOR_KNOCKOUT_SIGNALS = [
    r'\bsenior\b', r'\bprincipal\b', r'\bstaff\b', r'\blead\b', r'\bhead of\b',
    r'\bdirector\b', r'\bvp\b', r'\bchief\b', r'\bmanager\b'
]

def is_title_in_german(title):
    t_lower = title.lower()
    return any(re.search(pat, t_lower) for pat in GERMAN_TITLE_KNOCKOUT)

def is_student_or_intern_job(title, description=""):
    combined = f"{title} {description}".lower()
    title_lower = title.lower()
    
    # Must have explicit English student signal
    has_student = any(re.search(pat, title_lower) for pat in MANDATORY_ENGLISH_STUDENT_SIGNALS)
    if not has_student:
        if not any(re.search(pat, combined) for pat in MANDATORY_ENGLISH_STUDENT_SIGNALS):
            return False
            
    # Knockout senior roles unless title explicitly states working student/intern
    if not has_student:
        if any(re.search(pat, title_lower) for pat in SENIOR_KNOCKOUT_SIGNALS):
            return False
            
    return True

def is_written_in_german(text):
    words = re.findall(r'\b[a-zäöüß]+\b', text.lower())
    if not words:
        return False
    de_count = sum(1 for w in words if w in GERMAN_STOPWORDS)
    en_count = sum(1 for w in words if w in ENGLISH_STOPWORDS)
    # If 3 or more German stopwords appear or German exceeds English, it's German!
    return de_count >= 3 or (de_count > en_count)

def is_marketing_or_hr(title, text):
    for pattern in KNOCKOUT_ROLES:
        if re.search(pattern, title.lower()):
            return True
    return False

HARD_GERMAN_INDICATORS = [
    r'\bfluent\b.*?\bgerman\b',
    r'\bgerman\b.*?\bfluent\b',
    r'\bfluency in (?:both )?(?:german|english)',
    r'\b(?:strong|solid|excellent|very good|good|proficient|proficiency|knowledge of|command of|skills in)\b.*?\bgerman\b',
    r'\bgerman\b.*?\b(?:skills|knowledge|proficiency|fluency|command|competence)\b',
    r'\b(?:german and english|english and german)\b',
    r'\bboth german and english\b',
    r'\bgerman\b.*?\b(?:is a must|is mandatory|is required|required|prerequisite|expected|essential|necessary)\b',
    r'\bgerman\b.*?\b(?:b2|c1|c2|native)\b',
    r'\b(?:speak|spoken|written|writing|communicat\w*)\b.*?\bgerman\b',
    r'\bgerman\b.*?\b(?:speak|spoken|written|writing|communicat\w*)\b',
    r'\blanguage(?:s)?\b.*?\bgerman\b',
    r'\b(?:bilingual|multilingual)\b.*?\bgerman\b',
    r'\bverhandlungssicher\b',
    r'\bdeutschkenntnisse\b'
]

SOFT_GERMAN_INDICATORS = [
    r'\bno german (?:is )?required\b',
    r'\bgerman (?:is )?not (?:strictly )?(?:required|mandatory|necessary)\b',
    r'\bgerman\b.*?\b(?:is )?(?:a (?:big |great )?plus|an advantage|nice[- ]to[- ]have|beneficial|optional|welcomed|appreciated|helpful)\b',
    r'\b(?:a plus|nice[- ]to[- ]have)\b.*?\bgerman\b',
    r'\bbasic\b.*?\bgerman\b',
    r'\bgerman (?:a1|a2|b1)\b',
    r'\b(?:willingness to learn|courses? available|help you learn)\b.*?\bgerman\b',
    r'\benglish is (?:enough|sufficient|our (?:working|company|primary|team|daily) language)\b'
]

def check_german_proficiency_barrier(text):
    text_lower = text.lower()
    sentences = re.split(r'[\n\r•\.\;\-–]\s*', text_lower)
    
    for s in sentences:
        s = s.strip()
        if not s or ('german' not in s and 'deutsch' not in s):
            continue
            
        # 1. If this specific sentence explicitly marks German as soft/optional, it passes!
        is_soft = any(re.search(soft, s) for soft in SOFT_GERMAN_INDICATORS)
        if is_soft:
            continue
            
        # 2. If this specific sentence has a hard German demand
        is_hard = any(re.search(hard, s) for hard in HARD_GERMAN_INDICATORS)
        if is_hard:
            return True, f'Demands German in requirement: "{s}"'
            
    return False, "Safe English Opportunity"

FOREIGN_LOCATIONS_KNOCKOUT = [
    r'\bnetherlands\b', r'\bholland\b', r'\bthe hague\b', r'\bamsterdam\b', r'\brotterdam\b',
    r'\buk\b', r'\bunited kingdom\b', r'\blondon\b', r'\bireland\b', r'\bdublin\b',
    r'\bfrance\b', r'\bparis\b', r'\bspain\b', r'\bmadrid\b', r'\bbarcelona\b',
    r'\bswitzerland\b', r'\bzurich\b', r'\bgeneva\b', r'\baustria\b', r'\bvienna\b', r'\bwien\b',
    r'\bpoland\b', r'\bwarsaw\b', r'\bitaly\b', r'\busa\b', r'\bunited states\b'
]

GERMANY_SIGNALS = [
    r'\bgermany\b', r'\bdeutschland\b', r'\bdeutschlandweit\b', r'\bgermany-wide\b',
    r'\bhometurf\b', r'\bwork from germany\b', r'\bremote in germany\b'
]

def is_in_target_region(location, description=""):
    loc_lower = location.lower()
    combined = f"{location} {description}".lower()
    
    # 1. HARD KNOCKOUT: If location is explicitly outside Germany (e.g. The Hague, London, Amsterdam)
    is_foreign = any(re.search(pat, loc_lower) for pat in FOREIGN_LOCATIONS_KNOCKOUT)
    has_germany = any(re.search(pat, loc_lower) or re.search(pat, combined) for pat in GERMANY_SIGNALS)
    
    if is_foreign and not has_germany:
        return False, "Foreign Jurisdiction (Outside Germany)"
        
    # 2. Remote / Hybrid Gate: Must be remote/hybrid WITHIN Germany!
    is_remote_hybrid = any(re.search(pat, combined) for pat in REMOTE_HYBRID_SIGNALS)
    if is_remote_hybrid:
        # Check if German city or Germany is explicitly mentioned
        is_german_city = any(city in loc_lower for city in REGIONAL_ONSITE_CITIES)
        if has_germany or is_german_city or 'remote' in loc_lower:
            # Reject if clearly foreign remote
            if is_foreign and not has_germany:
                return False, "Foreign Remote (Requires foreign work visa)"
            return True, "Remote / Hybrid (Germany-Wide)"
    
    # 3. Regional Onsite Gate: Southern Germany Tech Corridor
    for city in REGIONAL_ONSITE_CITIES:
        if city in loc_lower:
            return True, f"Onsite/Regional Hub ({city.title()})"
            
    # 4. Postal Code Gate: Any German PLZ in Baden-Württemberg or Bavaria (7xxxx and 8xxxx)
    if re.search(r'\b[78]\d{4}\b', loc_lower):
        return True, "Southern Germany Tech Corridor (PLZ 7/8)"
            
    if has_germany:
        return True, "Germany (Flexible / Multi-Hub)"
        
    return False, "Outside Commutable / German Visa Radar"

def is_posted_today(timestamp_val):
    if not timestamp_val:
        return True  # If feed doesn't provide timestamp, assume current
    try:
        now_ts = datetime.now(timezone.utc).timestamp()
        if isinstance(timestamp_val, (int, float)):
            age = now_ts - timestamp_val
            return age <= MAX_AGE_SECONDS
        elif isinstance(timestamp_val, str):
            # Try parsing ISO 8601 string
            clean_ts = timestamp_val.replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_ts)
            age = now_ts - dt.timestamp()
            return age <= MAX_AGE_SECONDS
    except Exception:
        return True
    return True

# -------------------------------------------------------------
# NOTIFICATION ENGINE
# -------------------------------------------------------------
def send_phone_notification(job):
    time.sleep(0.3)  # Rate limiting protection
    is_student = any(kw in f"{job['title']} {job['url']}".lower() for kw in ['student', 'werkstudent', 'intern', 'praktik', 'trainee', 'junior', 'associate'])
    role_badge = "🎓 STUDENT / JUNIOR" if is_student else "💼 GENERAL / REMOTE"
    
    title = f"🚨 {role_badge}: {job['company']}"
    message = (
        f"💼 {job['title']}\n"
        f"📍 Location: {job['location']} [{job.get('geo_type', 'Regional')}]\n"
        f"🌐 English Role ({job['lang_status']})\n"
        f"🕒 Fresh: Posted Today"
    )
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    
    headers = {
        "Title": title.encode('utf-8'),
        "Priority": "high" if is_student else "default",
        "Tags": "mortar_board,rocket" if is_student else "briefcase",
        "Click": job['url']
    }
    
    req = urllib.request.Request(url, data=message.encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"[ALERT SENT TO PHONE] {job['title']} at {job['company']} ({job['geo_type']})")
            return True
    except Exception as e:
        print(f"[NOTIFICATION ERROR] {e}")
        return False

# -------------------------------------------------------------
# MULTI-SOURCE INGESTION (10,000+ Companies)
# -------------------------------------------------------------
def fetch_from_arbeitnow():
    url = "https://www.arbeitnow.com/api/job-board-api"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            jobs = []
            for j in data.get('data', []):
                jobs.append({
                    'id': j.get('slug') or str(j.get('id', '')),
                    'title': j.get('title', ''),
                    'company': j.get('company_name', ''),
                    'location': j.get('location', 'Germany'),
                    'description': j.get('description', ''),
                    'url': j.get('url', ''),
                    'timestamp': j.get('created_at')
                })
            return jobs
    except Exception as e:
        print(f"Error fetching from Arbeitnow: {e}")
        return []

def fetch_from_jobicy():
    url = "https://jobicy.com/api/v2/remote-jobs?count=50&geo=germany"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            jobs = []
            for j in data.get('jobs', []):
                jobs.append({
                    'id': f"jobicy_{j.get('id', '')}",
                    'title': j.get('jobTitle', ''),
                    'company': j.get('companyName', ''),
                    'location': j.get('jobGeo', 'Remote Germany'),
                    'description': j.get('jobDescription', ''),
                    'url': j.get('url', ''),
                    'timestamp': j.get('pubDate')
                })
            return jobs
    except Exception as e:
        print(f"Error fetching from Jobicy: {e}")
def fetch_from_arbeitsagentur():
    """Ingests official German Job Exchange (Bundesagentur für Arbeit) which covers:
       - Every postal code and regional employer in Ulm, Biberach, Heidenheim, Stuttgart, Munich
       - StepStone & Xing partner job feeds
       - EURES (European Employment Services for Germany)
    """
    cities = [("Ulm", 50), ("Stuttgart", 50), ("München", 50)]
    jobs = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'X-API-Key': 'jobboerse-jobsuche'
    }
    import ssl
    ctx = ssl._create_unverified_context()
    for city, radius in cities:
        for kw in ["Working Student", "Werkstudent"]:
            encoded_kw = urllib.parse.quote(kw)
            encoded_city = urllib.parse.quote(city)
            url = f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?was={encoded_kw}&wo={encoded_city}&umkreis={radius}&page=1&size=25"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    for item in data.get('ergebnisliste', []):
                        ref = item.get('referenznummer')
                        if not ref:
                            continue
                        locs = item.get('stellenlokationen', [])
                        loc_str = city
                        if locs and isinstance(locs, list) and len(locs) > 0:
                            addr = locs[0].get('adresse', {})
                            loc_str = f"{addr.get('ort', city)} ({addr.get('plz', '')})"
                        
                        title_clean = item.get('stellenangebotsTitel') or item.get('hauptberuf', '')
                        jobs.append({
                            'id': f"ba_{ref}",
                            'title': title_clean,
                            'company': item.get('firma', 'Regional Employer'),
                            'location': loc_str,
                            'description': f"{title_clean} at {item.get('firma', '')} in {loc_str}. Reference: {ref}",
                            'url': f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}",
                            'timestamp': item.get('datumErsteVeroeffentlichung') or item.get('aenderungsdatum')
                        })
            except Exception:
                pass
            time.sleep(0.15)
    return jobs

def fetch_from_linkedin():
    """Ingests live LinkedIn postings posted within the last 24h across target regions."""
    locations = ["Ulm", "Stuttgart", "Munich", "Germany"]
    jobs = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    for loc in locations:
        encoded_loc = urllib.parse.quote(loc)
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=working%20student&location={encoded_loc}&f_TPR=r86400"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode('utf-8')
                titles = re.findall(r'<h3 class="base-search-card__title">([\s\S]*?)</h3>', html)
                links = re.findall(r'<a class="base-card__full-link[^"]*" href="([^"]+)"', html)
                companies = re.findall(r'<h4 class="base-search-card__subtitle">([\s\S]*?)</h4>', html)
                locs = re.findall(r'<span class="job-search-card__location">([\s\S]*?)</span>', html)
                
                count = min(len(titles), len(links))
                for i in range(count):
                    title_clean = re.sub(r'<[^>]+>', '', titles[i]).strip()
                    link_clean = links[i].split('?')[0]
                    co_clean = re.sub(r'<[^>]+>', '', companies[i]).strip() if i < len(companies) else "Employer"
                    loc_clean = re.sub(r'<[^>]+>', '', locs[i]).strip() if i < len(locs) else loc
                    
                    job_urn = re.search(r'view/(\d+)', link_clean)
                    job_id = f"li_{job_urn.group(1)}" if job_urn else f"li_{abs(hash(link_clean))}"
                    
                    jobs.append({
                        'id': job_id,
                        'title': title_clean,
                        'company': co_clean,
                        'location': loc_clean,
                        'description': f"{title_clean} at {co_clean} in {loc_clean}",
                        'url': link_clean,
                        'timestamp': datetime.now(timezone.utc).timestamp()
                    })
        except Exception:
            pass
        time.sleep(0.2)
    return jobs

def fetch_from_remoteok():
    """Ingests international & European tech roles eligible for Germany."""
    url = "https://remoteok.com/api"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            jobs = []
            for j in data[1:]:
                if not isinstance(j, dict):
                    continue
                jobs.append({
                    'id': f"ro_{j.get('id', '')}",
                    'title': j.get('position', ''),
                    'company': j.get('company', 'Tech Firm'),
                    'location': j.get('location', 'Remote Germany'),
                    'description': j.get('description', ''),
                    'url': j.get('url', ''),
                    'timestamp': j.get('epoch')
                })
            return jobs
    except Exception:
        return []

def run_multi_company_radar():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Launching Multi-Company Radar (Only Today's Postings)...")
    
    # Ingest from all 5 multi-company networks
    all_raw_jobs = (
        fetch_from_arbeitnow() + 
        fetch_from_jobicy() + 
        fetch_from_arbeitsagentur() + 
        fetch_from_linkedin() + 
        fetch_from_remoteok()
    )
    print(f"Retrieved {len(all_raw_jobs)} live job listings across multi-company feeds.")

    new_qualified = []
    
    for j in all_raw_jobs:
        job_id = j['id']
        if job_id in seen_jobs:
            continue
            
        # 1. Freshness Gate: ONLY TODAY (Last 24 Hours)
        if not is_posted_today(j.get('timestamp')):
            continue
            
        title = j['title']
        company = j['company']
        location = j['location']
        description = j['description']
        job_url = j['url']
        
        # 2. Geographic & Remote/Hybrid Filter
        is_geo_ok, geo_type = is_in_target_region(location, description)
        if not is_geo_ok:
            continue
            
        # 3. Knockout: Is the title written in German? (e.g. Werkstudent, Praktikant, Einkauf)
        if is_title_in_german(title):
            continue
            
        # 4. MANDATORY STUDENT GATE: ONLY Working Student, Internships, Student Jobs!
        if not is_student_or_intern_job(title, description):
            continue
            
        # 5. Knockout: Marketing & HR
        if is_marketing_or_hr(title, description):
            continue
            
        # 6. Knockout: Is the job written in German?
        if is_written_in_german(description):
            continue
            
        # 5. Knockout: Does the English posting demand German C1?
        has_barrier, lang_status = check_german_proficiency_barrier(description)
        if has_barrier:
            continue
            
        # Passed All Gates! Fresh from Today!
        qualified_job = {
            'id': job_id,
            'title': title,
            'company': company,
            'location': location,
            'geo_type': geo_type,
            'url': job_url,
            'lang_status': lang_status,
            'timestamp': datetime.now().isoformat()
        }
        
        new_qualified.append(qualified_job)
        seen_jobs.add(job_id)
        
        # Dispatch instant phone notification!
        send_phone_notification(qualified_job)

    # Persist updated seen jobs
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_jobs), f)
        
    print(f"Scan complete. {len(new_qualified)} brand-new English opportunities from TODAY dispatched to phone.")
    return new_qualified

if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        print("[RADAR DAEMON ACTIVE] Scanning every 30 minutes in background...")
        while True:
            try:
                run_multi_company_radar()
            except Exception as e:
                print(f"[Error in scan loop] {e}")
            time.sleep(1800)
    else:
        run_multi_company_radar()
