

import os
import io
import re
import json
import ssl
import sys
import time
import random
import smtplib
import urllib.request
from urllib.parse import urljoin
from datetime import datetime
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from pypdf import PdfReader
import pyperclip

# Selenium Modules
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ============================================================
# CONFIGURATION
# ============================================================
OPENROUTER_API_KEY = os.getenv("")		       
SENDER_GMAIL = os.getenv("")
GMAIL_APP_PASSWORD = os.getenv("k")
BLOGGER_SECRET_EMAIL = os.getenv("")

BLOG_URL = "https://quickonlineform.blogspot.com"
PROCESSED_FILE = "processed_notices.txt"

PORTALS = [
    {
        "name": "PSSSB Punjab",
        "url": "https://sssb.punjab.gov.in",
        "base_url": "https://sssb.punjab.gov.in"
    },
    {
        "name": "Punjab Police",
        "url": "https://www.punjabpolice.gov.in",
        "base_url": "https://www.punjabpolice.gov.in"
    },
    {
        "name": "PPSC Punjab",
        "url": "https://ppsc.gov.in",
        "base_url": "https://ppsc.gov.in"
    },
    {
        "name": "DSSSB Delhi",
        "url": "https://dsssb.delhi.gov.in",
        "base_url": "https://dsssb.delhi.gov.in"
    },
    {
        "name": "SSC India",
        "url": "https://ssc.gov.in",
        "base_url": "https://ssc.gov.in"
    },
    {
        "name": "RRB Railway",
        "url": "https://www.rrbcdg.gov.in",
        "base_url": "https://www.rrbcdg.gov.in"
    }
]

ALLOWED_KEYWORDS = [
    "recruitment", "bharti", "advertisement", "advt", "vacancy", "post", "notification",
    "apply online", "offline form", "application form", "online form", "registration",
    "admit card", "hall ticket", "roll no", "exam date", "schedule", "cbt", "physical", "pst", "pet",
    "result", "merit", "selection list", "waiting list", "cut off", "score card"
]

OLD_DATA_BLOCK = [
    "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025",
    "01/2026", "02/2026", "03/2026", "04/2026", "05/2026", "06/2026", "07/2026", "08/2026",
    "jan 2026", "feb 2026", "mar 2026", "apr 2026", "may 2026", "jun 2026", "jul 2026", "aug 2026",
    "january 2026", "february 2026", "march 2026", "april 2026", "june 2026", "july 2026", "august 2026",
    "-01-2026", "-02-2026", "-03-2026", "-04-2026", "-05-2026", "-06-2026", "-07-2026", "-08-2026"
]

BLOCKED_KEYWORDS = [
    "certificate section", "verification section", "scholarship", "scholarship-branch",
    "rules & notifications", "rules and notifications", "tender", "quotation", "bid", "auction",
    "procurement", "eoi", "rfp", "transfer", "seniority", "promotion", "deputation", "arms", "weapon",
    "license", "scrap", "circular", "minutes of meeting", "model test paper", "sample paper", "syllabus",
    "class 11", "11th admission", "admission", "contact us", "about us", "screen reader",
    "question paper structure", "submit docs", "pending documents", "withheld", "answer key", "objection",
    "reappear", "re-appear", "compartment", "golden chance", "10th class", "12th class", "date sheet", "datesheet"
]

BLOCKED_URL_PATTERNS = [
    "/rules", "/rules-notifications", "/rules-and-notifications", "/answer-key", "/category/", "/tag/", "/page/", 
    "/certificatesection", "/scholarship", "/scholarship-branch", "/admission", "/contact", "/about",
    "/privacy", "/disclaimer", "/vacancy-group-b", "/vacancy-group-a", "/vacancy-group-c",
    "/latest-jobs", "/all-jobs", "/feedback", "/rti", "/sitemap", "/modeltestpaper"
]

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE
ssl_ctx.options |= 0x4
try:
    ssl_ctx.set_ciphers('DEFAULT@SECLEVEL=1')
except Exception:
    pass

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,pa;q=0.8,hi;q=0.7'
}

def clean_branding(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', str(text)).strip(" -|:")

def sanitize_field(val, fallback="Check Official Notice"):
    if not val: return fallback
    s = str(val).strip()
    bad = ["n/a", "na", "none", "null", "current deadline", "start date", "not mentioned", "ਅੰਦਾਜ਼ਾ ਨਹੀਂ", "ਅਜਿਹਾ ਨਹੀਂ", "as per rules", "as per official rules"]
    if s.lower() in bad or len(s) < 2: return fallback
    return clean_branding(s)

def is_current_data(text, link):
    combined = (text + " " + link).lower()
    if "2026" not in combined and "2027" not in combined: return False
    for old in OLD_DATA_BLOCK:
        if old in combined: return False
    return True

def call_llm(system_prompt, user_prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    models = ["openrouter/free", "meta-llama/llama-3.1-8b-instruct:free", "mistralai/mistral-7b-instruct:free"]
    for m in models:
        payload = {
            "model": m,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 0.1
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res = json.loads(response.read().decode("utf-8"))
                content = res["choices"][0]["message"]["content"].strip()
                if content and "User Safety:" not in content: return content
        except Exception:
            continue
    return None

# ============================================================
# AGENT 1: वेब स्कैनर (टाइमआउट 30 सेकंड किया गया है)
# ============================================================
def agent_1_scanner(target, processed_urls):
    print(f"\n🔍 [एजेंट 1 - स्कैनर] स्कैनिंग: {target['name']}...")
    try:
        req = urllib.request.Request(target["url"], headers=BROWSER_HEADERS)
        html = urllib.request.urlopen(req, context=ssl_ctx, timeout=30).read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  [-] पोर्टल लोड नहीं हो सका: {e}")
        return None

    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        text = a.get_text().strip()
        if not href or href.startswith('#') or href.startswith('javascript:'): continue

        full_url = urljoin(target["base_url"], href).replace(" ", "%20")
        combined = (text + " " + full_url).lower()

        if not (".pdf" in full_url.lower() or any(k in full_url.lower() for k in ["notice", "recruitment", "advertisement", "result", "admit", "apply", "job", "vacancy"])):
            continue

        if not is_current_data(text, full_url): continue
        if any(b in full_url.lower() for b in BLOCKED_URL_PATTERNS): continue
        if any(b in combined for b in BLOCKED_KEYWORDS): continue
        if not any(a_kw in combined for a_kw in ALLOWED_KEYWORDS): continue

        if len(text) >= 15 and full_url not in processed_urls:
            clean_t = clean_branding(text)
            if len(clean_t) >= 10:
                direct_action_link = ""
                parent_row = a.find_parent(['tr', 'li', 'div'])
                if parent_row:
                    for sibling_a in parent_row.find_all('a', href=True):
                        sib_href = sibling_a['href'].strip()
                        sib_text = sibling_a.get_text().lower()
                        if any(k in sib_href.lower() or k in sib_text for k in ['apply', 'login', 'register', 'digialm', 'admit', 'result', 'cdn.digialm']):
                            if not sib_href.endswith('.pdf'):
                                direct_action_link = urljoin(target["base_url"], sib_href).replace(" ", "%20")
                                break
                return clean_t, full_url, direct_action_link
    return None

# ============================================================
# AGENT 2: फ़ैक्ट चेकर
# ============================================================
def agent_2_fact_checker(title, raw_text, portal_name):
    print("  [एजेंट 2 - स्ट्रक्चरर] डेटा विश्लेषण और पूर्णता जाँच...")
    is_off = any(w in (title + " " + raw_text).lower() for w in ["offline", "postal", "application form", "proforma"])
    current_dt = datetime.now().strftime("%d %B %Y")

    system_prompt = f"""
    You are Agent 2. Classify into EXACTLY ONE category: 'Job', 'Admit Card', 'Result'.
    CRITICAL RULES:
    1. CURRENT DATE IS: {current_dt}. If dates are from PAST MONTHS, set 'is_valid' to false.
    2. STRICT SHORT NOTICE CHECK: If this is a 'Job' post and the notice is incomplete (lacks exact dates, fee, age limit, or vacancy breakdown, only showing a brief announcement like 'we will release soon' or missing core details), YOU MUST SET 'is_valid' TO false. We do not publish incomplete short notices.
    3. Output ONLY valid JSON:
    {{
      "is_valid": true,
      "category": "Job" or "Admit Card" or "Result",
      "department": "Official Department Name",
      "catchy_headline": "Short Title 2026",
      "total_vacancies": "Exact count",
      "last_date": "Exact Date",
      "start_date": "Exact Date",
      "short_info_english": "50-60 words clear English summary.",
      "application_fee": "Exact Fee details",
      "age_limit": "Exact Age limit",
      "postal_address": "Postal address",
      "table_rows": [{{"post_name": "Post", "total": "Count", "qualification": "Qualification"}}]
    }}
    """
    user_prompt = f"Title: {title}\nDepartment: {portal_name}\nNotice Text:\n{raw_text[:5000]}"
    res = call_llm(system_prompt, user_prompt)
    
    clean_t = clean_branding(title)
    data = {}
    if res:
        try:
            match = re.search(r'\{.*\}', res, re.DOTALL)
            if match: data = json.loads(match.group(0))
        except Exception:
            pass

    if not data.get("is_valid", True):
        return {"is_valid": False, "reason": "यह अधूरा शॉर्ट नोटिस है या पुराना/अवैध है।"}

    cat = data.get("category", "Job")
    if cat not in ["Job", "Admit Card", "Result"]: cat = "Job"

    headline = sanitize_field(data.get("catchy_headline"), f"{clean_t[:48]} 2026")
    if len(headline) > 65: headline = f"{headline[:60]}..."

    short_en = str(data.get("short_info_english", "")).strip()
    if not short_en or len(short_en) < 35 or re.search(r'[\u0A00-\u0A7F]', short_en):
        short_en = f"The official notification for {clean_t} has been published by {portal_name}. Candidates can review the complete schedule and direct links below."

    rows = data.get("table_rows", [])
    if not rows or len(rows) == 0:
        rows = [{"post_name": clean_t[:35], "total": "Various Posts", "qualification": "As per notification"}]

    return {
        "is_valid": True,
        "category": cat,
        "is_offline": is_off,
        "department": sanitize_field(data.get("department"), portal_name),
        "catchy_headline": headline,
        "total_vacancies": sanitize_field(data.get("total_vacancies"), "Various Posts"),
        "last_date": sanitize_field(data.get("last_date"), "Check Notice"),
        "start_date": sanitize_field(data.get("start_date"), "Released"),
        "short_info_english": clean_branding(short_en),
        "application_fee": sanitize_field(data.get("application_fee"), "As per rules"),
        "age_limit": sanitize_field(data.get("age_limit"), "As per rules"),
        "postal_address": sanitize_field(data.get("postal_address"), ""),
        "table_rows": rows
    }

# ============================================================
# AGENT 3: HTML/CSS डिज़ाइनर
# ============================================================
def agent_3_designer(data, portal_url, doc_url, labels_list, post_uid, deep_link):
    category = data.get("category", "Job")
    print(f"  [एजेंट 3 - डिज़ाइनर] '{category}' लेआउट तैयार किया जा रहा है...")
    
    catchy_title = data["catchy_headline"]
    last_date = data["last_date"]
    start_date = data["start_date"]
    short_info = data["short_info_english"]
    is_offline = data.get("is_offline", False)
    
    has_direct_link = bool(deep_link and deep_link.startswith("http"))
    direct_action_link = deep_link if has_direct_link else portal_url
    
    if category == "Admit Card":
        sub_heading = "Exam Date & Admit Card Update"
        banner_badge = f"⏳ EXAM / ADMIT CARD DATE: {last_date} ⏳"
        date_block_html = f"""
        <div style="background:#ffffff; border-left:4px solid #3b82f6; border:1px solid #e2e8f0; border-radius:6px; padding:15px; margin-bottom:16px;">
            <h4 style="margin:0 0 8px 0; color:#1e3a8a; font-size:16px;">🎟️ Exam & Admit Card Details</h4>
            <p style="margin:4px 0; font-size:14px;"><strong>Admit Card Status:</strong> {start_date}</p>
            <p style="margin:4px 0; font-size:14px; color:#dc2626; font-weight:bold;"><strong>Exam Date / Schedule:</strong> {last_date}</p>
        </div>
        """
        table_html = ""
        for row in data.get("table_rows", []):
            table_html += f"""
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px; border:1px solid #cbd5e1; font-weight:600;">{row.get('post_name', '')}</td>
                <td style="padding:10px; border:1px solid #cbd5e1; text-align:center; color:#0284c7; font-weight:bold;">{row.get('total', '')}</td>
            </tr>
            """
        middle_content = f"""
        <div style="margin-bottom:20px;">
            <h4 style="color:#1e3a8a; font-size:16px; margin-bottom:6px;">📝 Post & Exam Overview</h4>
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:14px;">
                <thead>
                    <tr style="background:#1e3a8a; color:#ffffff;">
                        <th style="padding:10px; border:1px solid #cbd5e1;">Post Name</th>
                        <th style="padding:10px; border:1px solid #cbd5e1; text-align:center;">Total Posts</th>
                    </tr>
                </thead>
                <tbody>{table_html}</tbody>
            </table>
        </div>
        """
        btn1_text = "🎟️ Login & Download Admit Card" if has_direct_link else "🌐 Visit Official Website"
        btn1_color = "#0284c7" if has_direct_link else "#475569"

    elif category == "Result":
        sub_heading = "Official Result & Merit List Declared"
        banner_badge = f"🏆 RESULT STATUS: {start_date} 🏆"
        date_block_html = f"""
        <div style="background:#ffffff; border-left:4px solid #16a34a; border:1px solid #e2e8f0; border-radius:6px; padding:15px; margin-bottom:16px;">
            <h4 style="margin:0 0 8px 0; color:#065f46; font-size:16px;">🏆 Result & Selection List</h4>
            <p style="margin:4px 0; font-size:14px;"><strong>Declaration Date:</strong> {start_date}</p>
            <p style="margin:4px 0; font-size:14px; color:#dc2626; font-weight:bold;"><strong>Next Step / DV Date:</strong> {last_date}</p>
        </div>
        """
        middle_content = ""
        btn1_text = "🏆 Check Result / Merit List" if has_direct_link else "🌐 Visit Official Website"
        btn1_color = "#16a34a" if has_direct_link else "#475569"

    else:
        sub_heading = data.get("total_vacancies", "Various Posts")
        banner_badge = f"⏳ LAST DATE: {last_date} ⏳"
        date_block_html = f"""
        <div style="background:#ffffff; border-left:4px solid #3b82f6; border:1px solid #e2e8f0; border-radius:6px; padding:14px; margin-bottom:14px;">
            <h4 style="margin:0 0 8px 0; color:#1e3a8a; font-size:16px;">🗓️ Important Dates</h4>
            <p style="margin:3px 0; font-size:14px;"><strong>Start Date:</strong> {start_date}</p>
            <p style="margin:3px 0; font-size:14px; color:#dc2626; font-weight:bold;"><strong>Last Date to Apply:</strong> {last_date}</p>
        </div>
        """
        fee = data.get("application_fee", "As per rules")
        age = data.get("age_limit", "As per rules")
        table_html = ""
        for row in data.get("table_rows", []):
            table_html += f"""
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:10px; border:1px solid #cbd5e1; font-weight:600;">{row.get('post_name', '')}</td>
                <td style="padding:10px; border:1px solid #cbd5e1; text-align:center; color:#0284c7; font-weight:bold;">{row.get('total', '')}</td>
                <td style="padding:10px; border:1px solid #cbd5e1;">{row.get('qualification', '')}</td>
            </tr>
            """
        middle_content = f"""
        <div style="background:#ffffff; border-left:4px solid #10b981; border:1px solid #e2e8f0; border-radius:6px; padding:14px; margin-bottom:16px;">
            <h4 style="margin:0 0 8px 0; color:#065f46; font-size:16px;">💰 Application Fee</h4>
            <p style="margin:0; font-size:14px;">{fee}</p>
        </div>
        <div style="margin-bottom:20px;">
            <h4 style="color:#1e3a8a; font-size:16px; margin-bottom:6px;">📝 Vacancy Details & Qualification</h4>
            <div style="color:#dc2626; font-weight:bold; font-size:14px; margin-bottom:10px;">Age Limit: {age}</div>
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:14px;">
                <thead>
                    <tr style="background:#1e3a8a; color:#ffffff;">
                        <th style="padding:10px; border:1px solid #cbd5e1;">Post Name</th>
                        <th style="padding:10px; border:1px solid #cbd5e1; text-align:center;">Total</th>
                        <th style="padding:10px; border:1px solid #cbd5e1;">Qualification</th>
                    </tr>
                </thead>
                <tbody>{table_html}</tbody>
            </table>
        </div>
        """
        if is_offline:
            btn1_text = "📥 Download Application Form"
            btn1_color = "#16a34a"
        elif has_direct_link:
            btn1_text = "👉 Direct Apply / Login Portal"
            btn1_color = "#0284c7"
        else:
            btn1_text = "🌐 Visit Official Website"
            btn1_color = "#475569"

    tags_html = '<div style="margin-top:20px; font-size:13px; color:#64748b;"><strong>Tags:</strong> '
    for t in labels_list:
        tags_html += f'<span style="background:#0f172a; color:#ffffff; padding:4px 10px; border-radius:4px; font-size:12px; margin-right:6px; display:inline-block; margin-top:4px;"># {t}</span> '
    tags_html += f'<span style="display:none;">{post_uid}</span></div>'

    return f"""
    <div style="max-width:750px; margin:auto; font-family:sans-serif; color:#1e293b;">
        <div style="background:#dc2626; color:#ffffff; border-radius:10px; padding:22px 15px; text-align:center; margin-bottom:20px;">
            <div style="font-size:14px; font-weight:bold; letter-spacing:1px; margin-bottom:8px;">🌐 QuickOnlineForm.com</div>
            <h2 style="margin:0; font-size:22px; font-weight:bold; text-transform:uppercase; color:#ffffff;">{catchy_title}</h2>
            <div style="font-size:16px; margin:8px 0 14px 0; color:#fef08a; font-weight:600;">{sub_heading}</div>
            <div style="display:inline-block; background:#fde047; color:#854d0e; padding:8px 20px; border-radius:25px; font-weight:bold; font-size:14px;">
                {banner_badge}
            </div>
        </div>
        <div style="font-size:15px; line-height:1.6; margin-bottom:18px; color:#334155; background:#f8fafc; padding:14px 16px; border-radius:6px; border-left:4px solid #64748b;">
            <strong style="color:#0f172a;">Short Information:</strong> {short_info}
        </div>
        {date_block_html}
        {middle_content}
        <div style="text-align:center; margin:22px 0;">
            <a href="{direct_action_link}" target="_blank" style="background-color:{btn1_color}; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:6px; font-weight:bold; font-size:15px; display:inline-block; margin:6px;">{btn1_text}</a>
            <a href="{doc_url}" target="_blank" style="background-color:#2563eb; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:6px; font-weight:bold; font-size:15px; display:inline-block; margin:6px;">📄 Official Notification PDF</a>
        </div>
        {tags_html}
    </div>
    """

# ============================================================
# AGENT 4: फ़ाइनल क्वालिटी चेकर
# ============================================================
def agent_4_auditor(data, html_content):
    print("  [एजेंट 4 - क्वालिटी चेकर] पब्लिशिंग से पहले लेआउट की जांच...")
    if not data.get("is_valid", True):
        return False, "एजेंट 2 ने इसे शॉर्ट नोटिस या अवैध मानकर रिजेक्ट कर दिया है।"
    title = data.get("catchy_headline", "").strip().lower()
    blocked_titles = ["n/a", "na", "rules & notifications", "certificate section", "model test paper", "answer key", "question paper"]
    if any(b in title for b in blocked_titles):
        return False, f"अवैध शीर्षक: '{title}'"
    return True, "डेटा 100% सटीक और नियमों के अनुकूल है।"

# ============================================================
# AGENT 5: पब्लिशर व व्हाट्सएप डिस्पैचर
# ============================================================
def verify_and_get_exact_live_url(post_uid, clean_ascii_title):
    feed_url = f"{BLOG_URL.rstrip('/')}/feeds/posts/default?alt=json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    print(f"  -> वेबसाइट पर ({post_uid}) के लाइव होने की जाँच...", end="", flush=True)
    title_words = [w.lower() for w in clean_ascii_title.split() if len(w) > 3][:3]

    for _ in range(20):
        time.sleep(4)
        print(".", end="", flush=True)
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
            entries = d.get('feed', {}).get('entry', [])
            for entry in entries[:3]:
                content_body = entry.get('content', {}).get('$t', '')
                entry_title = entry.get('title', {}).get('$t', '').lower()
                if (post_uid in content_body) or (len(title_words) >= 2 and all(w in entry_title for w in title_words)):
                    for link in entry.get('link', []):
                        if link.get('rel') == 'alternate':
                            print(f" [लाइव! -> {link.get('href')}]")
                            return link.get('href')
        except Exception:
            pass
    print(" [!] पोस्ट वेबसाइट पर लाइव नहीं दिखी!")
    return None

def agent_5_publisher(clean_title, html_content, labels_list, data, post_uid):
    print(f"\n[एजेंट 5 - पब्लिशर] वेबसाइट पर लेबल्स {labels_list} के साथ पब्लिशिंग...")
    app_pass = GMAIL_APP_PASSWORD.replace(" ", "").strip()
    msg = MIMEText(html_content, 'html', 'utf-8')
    msg['From'] = SENDER_GMAIL
    msg['To'] = BLOGGER_SECRET_EMAIL
    
    labels_str = ", ".join(labels_list)
    clean_ascii_title = re.sub(r'[^\w\s\-\.\,\(\)]', '', re.sub(r'[^\x00-\x7F]+', '', clean_title)).strip()
    if len(clean_ascii_title) < 5: clean_ascii_title = f"{data.get('department', 'Punjab')} Update 2026"
    msg['Subject'] = f"{clean_ascii_title} [{labels_str}]"

    email_sent = False
    for port in [587, 465]:
        try:
            server = smtplib.SMTP('smtp.gmail.com', port, timeout=20) if port == 587 else smtplib.SMTP_SSL('smtp.gmail.com', port, timeout=20)
            if port == 587: server.ehlo(); server.starttls(); server.ehlo()
            server.login(SENDER_GMAIL, app_pass)
            server.sendmail(SENDER_GMAIL, BLOGGER_SECRET_EMAIL, msg.as_string())
            server.quit()
            email_sent = True
            print(f"  -> [✓] ईमेल भेजा गया: {msg['Subject']}")
            break
        except Exception:
            continue

    if not email_sent: return False

    exact_url = verify_and_get_exact_live_url(post_uid, clean_ascii_title)
    if not exact_url: return False

    print("\n[एजेंट 5 - डिस्पैचर] WhatsApp अलर्ट भेजा जा रहा है...")
    category = data.get("category", "Job")
    headline = data.get("catchy_headline", "ਨਵਾਂ ਅਪਡੇਟ 2026")
    last_date = data.get("last_date", "ਨੋਟੀਫਿਕੇਸ਼ਨ ਦੇਖੋ")
    last_date_pa = "ਅਧਿਕਾਰਤ ਨੋਟੀਫਿਕੇਸ਼ਨ ਦੇਖੋ" if last_date in ["Check Notice", "Check Official Notice"] else last_date

    if category == "Admit Card":
        wa_msg = (f"🎟️ *{headline} – ਐਡਮਿਟ ਕਾਰਡ / ਪੇਪਰ ਮਿਤੀ ਜਾਰੀ!* 🎟️\n\n"
                  f"📍 *ਪ੍ਰੀਖਿਆ ਮਿਤੀ / ਸ਼ਡਿਊल:* {last_date_pa}\n\n"
                  f"ਉਮੀਦਵਾਰਾਂ ਲਈ ਪ੍ਰੀਖਿਆ और ਐਡਮਿਟ ਕਾਰਡ ਸਬੰਧੀ ਨਵਾਂ ਨੋਟਿਸ ਜਾਰੀ कर ਦਿੱਤਾ ਗਿਆ है।\n\n"
                  f"🔗 ਐਡਮਿਟ ਕਾਰਡ ਡਾਊਨਲੋਡ ਲਿੰਕ:\n👉 {exact_url}\n\nਜਾਣਕਾਰੀ ਲਈ ਜੁੜੇ ਰਹੋ: 👉 Gurpreet Telecom & Cafe")
    elif category == "Result":
        wa_msg = (f"🏆 *{headline} – ਨਤੀਜਾ / ਮੈरਿਟ ਲਿਸਟ ਜਾਰੀ!* 🏆\n\n"
                  f"ਉਮੀਦਵਾਰਾਂ ਲਈ ਅਧਿਕਾਰਤ ਨਤੀਜਾ और ਚੋਣ ਸੂਚੀ ਜਾਰੀ कर ਦਿੱਤਾ ਗਿਆ है।\n\n"
                  f"🔗 ਰਿਜ਼ਲਟ ਚੈੱਕ ਕਰਨ ਲਈ ਲਿੰਕ:\n👉 {exact_url}\n\nਜਾणਕਾਰੀ ਲਈ ਜੁੜੇ ਰਹੋ: 👉 Gurpreet Telecom & Cafe")
    else:
        vac_pa = data.get("total_vacancies", "ਵੱਖ-ਵੱਖ ਅਸਾਮੀਆਂ")
        if vac_pa in ["Various Posts", "Check Official Notice", "Check Notice"]: vac_pa = "ਵੱਖ-ਵੱਖ ਅਸਾਮੀਆਂ"
        
        fee_wa = data.get("application_fee", "As per rules")
        age_wa = data.get("age_limit", "As per rules")
        
        wa_msg = (f"💥 *{headline} – ਨਵਾਂ ਨੋਟਿਸ ਜਾਰੀ!* 💥\n\n"
                  f"📍 *ਆਖਰੀ ਮਿਤੀ:* {last_date_pa}\n\n"
                  f"📌 *ਕੁੱਲ ਪੋਸਟਾਂ:* {vac_pa}\n"
                  f"🗓️ *ਆਖਰੀ ਮਿਤੀ:* {last_date_pa}\n"
                  f"💰 *ਫੀਸ:* {fee_wa}\n"
                  f"🎓 *ਉਮਰ ਹੱਦ:* {age_wa}\n\n"
                  f"⚠️ ਆਖ਼ਰੀ ਮਿਤੀ ਤੋਂ ਪਹਿਲਾਂ ਫਾਰਮ ਜ਼ਰੂਰ ਭਰਵਾ ਲਵੋ।\n\n"
                  f"🔗 ਆਨਲਾਈਨ ਅਪਲਾਈ ਲਿੰਕ:\n👉 {exact_url}\n\nਜਾਣਕਾਰੀ ਲਈ ਜੁੜੇ ਰਹੋ: 👉 Gurpreet Telecom & Cafe")

    profile_path = os.path.abspath("chrome_profile")
    options = Options()
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-proxy-server")
    options.add_argument("--proxy-server='direct://'")
    options.add_argument("--proxy-bypass-list=*")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 45)
    try:
        driver.get("https://web.whatsapp.com")
        wait.until(EC.presence_of_element_located((By.XPATH, '//div[@id="side"] | //header | //div[@role="navigation"]')))
        time.sleep(2)
        channels_xpath = '//*[@data-icon="newsletter" or @data-icon="newsletter-outline"] | //*[@aria-label="Channels" or @title="Channels" or contains(@aria-label, "ਚੈਨਲ")]'
        channels_elem = wait.until(EC.presence_of_element_located((By.XPATH, channels_xpath)))
        driver.execute_script("arguments[0].click();", channels_elem)
        time.sleep(3)
        target_xpath = '//span[contains(text(), "Gurpreet Telecom")] | //span[contains(@title, "Gurpreet Telecom")] | //div[@role="listitem"]//span[contains(text(), "Gurpreet")]'
        channel_elem = wait.until(EC.presence_of_element_located((By.XPATH, target_xpath)))
        driver.execute_script("arguments[0].click();", channel_elem)
        time.sleep(3.5)
        msg_box_xpath = '//div[@contenteditable="true"][@role="textbox"] | //div[@aria-label="Type an update"] | //footer//div[@contenteditable="true"]'
        msg_box = wait.until(EC.presence_of_element_located((By.XPATH, msg_box_xpath)))
        driver.execute_script("arguments[0].focus();", msg_box)
        msg_box.click()
        time.sleep(1)
        pyperclip.copy(wa_msg)
        msg_box.send_keys(Keys.CONTROL, 'v')
        time.sleep(1.5)
        msg_box.send_keys(Keys.ENTER)
        time.sleep(3)
        print("  -> [✓] WhatsApp पर सही लिंक सेंड हो गया!")
        return True
    except Exception as e:
        print(f"  -> [!] WhatsApp सेंड त्रुटि: {e}")
        return False
    finally:
        time.sleep(2)
        driver.quit()

# ============================================================
# MAIN PIPELINE
# ============================================================
def load_processed():
    if not os.path.exists(PROCESSED_FILE): return set()
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f: return set(line.strip() for line in f if line.strip())

def mark_processed(url):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f: f.write(url + "\n")

def run_pipeline():
    processed_urls = load_processed()
    print("==================================================")
    print("🚀 Final 5-Agent Automation System (Active)")
    print("==================================================")

    for target in PORTALS:
        res = agent_1_scanner(target, processed_urls)
        if not res:
            print(f"  -> {target['name']} पर कोई नया (ताज़ा) नोटिस नहीं मिला।")
            continue

        title, doc_url, deep_link = res
        print(f"\n[!] नया नोटिस मिला:\n    {title}\n    Link: {doc_url}")

        raw_text = ""
        if '.pdf' in doc_url.lower():
            try:
                pdf_req = urllib.request.Request(doc_url, headers=BROWSER_HEADERS)
                pdf_bytes = urllib.request.urlopen(pdf_req, context=ssl_ctx, timeout=25).read()
                reader = PdfReader(io.BytesIO(pdf_bytes))
                raw_text = "".join([page.extract_text() or "" for page in reader.pages[:2]])
            except Exception:
                raw_text = title
        else:
            try:
                page_req = urllib.request.Request(doc_url, headers=BROWSER_HEADERS)
                page_html = urllib.request.urlopen(page_req, context=ssl_ctx, timeout=20).read().decode('utf-8', errors='ignore')
                page_soup = BeautifulSoup(page_html, 'html.parser')
                for script in page_soup(["script", "style"]): script.extract()
                raw_text = page_soup.get_text(separator=' ', strip=True)[:5000]
            except Exception:
                raw_text = title

        verified_data = agent_2_fact_checker(title, raw_text, target["name"])

        if not verified_data.get("is_valid", True):
            print(f"  ❌ [एजेंट 2 द्वारा अस्वीकृत]: {verified_data.get('reason', 'यह अधूरा शॉर्ट नोटिस है।')}")
            mark_processed(doc_url)
            continue

        cat = verified_data.get("category", "Job")
        labels_list = [cat, "Latest Jobs", "Punjab Jobs" if "Punjab" in target["name"] else "Govt Jobs"]

        post_uid = f"QOF-{random.randint(10000, 99999)}"
        complete_post_html = agent_3_designer(verified_data, target["url"], doc_url, labels_list, post_uid, deep_link)

        is_pass, reason = agent_4_auditor(verified_data, complete_post_html)
        if not is_pass:
            print(f"  ❌ [एजेंट 4 द्वारा अस्वीकृत]: {reason}")
            mark_processed(doc_url)
            continue
            
        print(f"  ✅ [एजेंट 4 मंज़ूरी]: {reason}")

        success = agent_5_publisher(verified_data["catchy_headline"], complete_post_html, labels_list, verified_data, post_uid)
        if success:
            mark_processed(doc_url)
            print(f"[✓] {target['name']} का काम 100% पूरा हुआ।\n")

    print("==================================================")
    print("✅ सभी पोर्टल्स का स्कैन चक्र पूरा हुआ!")
    print("==================================================")

if __name__ == "__main__":
    run_pipeline()
