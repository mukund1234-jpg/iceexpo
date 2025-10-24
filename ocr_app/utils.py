import re
import phonenumbers
from paddleocr import PaddleOCR
from transformers import pipeline
import spacy

# ----------------------------
# NER MODELS
# ----------------------------
# English NER (optional)
nlp = spacy.load("en_core_web_sm")

# Multilingual NER (supports Marathi, Hindi, English, etc.)
ner_model = pipeline( "ner", 
                           model="Davlan/xlm-roberta-large-ner-hrl",
                            aggregation_strategy="simple" )

# ----------------------------
# OCR MODEL
# ----------------------------
ocr = PaddleOCR(use_angle_cls=False, lang='mr')  # Marathi OCR



def extract_text(image_path):
    result = ocr.ocr(image_path)
    text_lines = []
    confidence_scores = []
    structured_result = []

    # PaddleOCR result format (from your logs)
    for page in result:  # result is a list with one dict per page/image
        rec_texts = page.get('rec_texts', [])
        # print("Recognized Texts:", rec_texts)
        rec_scores = page.get('rec_scores', [])
        rec_boxes = page.get('rec_boxes', [])

        page_structured = []
        for i, text in enumerate(rec_texts):
            score = rec_scores[i] if i < len(rec_scores) else 0.0
            bbox = rec_boxes[i] if i < len(rec_boxes) else None
            page_structured.append([bbox, (text, score)])
            text_lines.append(text)
            confidence_scores.append(score)

        structured_result.append(page_structured)

    # Join all text lines
    text = "\n".join(text_lines)
    # print("Extracted Text:", text)
    return text
# ----------------------------
# CLEAN OCR TEXT
# ----------------------------
def clean_ocr_text(text):
    junk_patterns = [
        r'^[\W_]+$',                # only punctuation or symbols
        r'^[eE\s]+$',               # just "e" or "E" or spaces
        r'^[wy]+$',                 # random isolated letters
        r'^[\|\[\]\{\}\<\>]+$',     # only brackets
        r'^[a-zA-Z]{1,3}$',         # short random English chars
        r'^[\u0900-\u097F]{1,2}$',  # very short Marathi/Hindi fragments
    ]

    cleaned_lines = []
    for line in text.split("\n"):
        l = line.strip().replace('\xa0', '').replace('\u200b', '')
        if not l:
            continue

        # Skip obvious junk patterns
        if any(re.match(p, l) for p in junk_patterns):
            continue

        # Skip lines that mix Devanagari and English randomly (likely noise)
        if re.search(r'[a-zA-Z]', l) and re.search(r'[\u0900-\u097F]', l):
            # But allow if it contains digits (addresses often do)
            if not re.search(r'\d', l):
                continue

        # Skip lines that are too short (less than 2 chars) and don't contain digits
        if len(l) < 2 and not re.search(r'\d', l):
            continue

        cleaned_lines.append(l)

    return "\n".join(cleaned_lines)

# ----------------------------
# EXTRACTORS
# ----------------------------
def extract_name(text):
    import re

    # Split text into non-empty lines
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    first_five_lines = "\n".join(lines[:5])
    print(first_five_lines)

    # --- Extract name from first 5 lines using NER ---
    entities = ner_model(first_five_lines)
    names = [ent['word'] for ent in entities if ent['entity_group'] in ['PER', 'PERSON', 'PER']]
    names = list(dict.fromkeys(names))  # remove duplicates

    # --- Remove lines containing extracted names ---
    name_keywords = [re.escape(n) for n in names]
    name_pattern = re.compile("|".join(name_keywords), re.I) if names else None

    remaining_lines = []
    for i, line in enumerate(lines):
        if i < 5 and name_pattern and name_pattern.search(line):
            continue  # skip lines containing detected names
        remaining_lines.append(line)

    cleaned_text = "\n".join(remaining_lines)

    return list(set(names))


def extract_company(text):
    entities = ner_model(text)
    orgs = [ent['word'] for ent in entities if ent['entity_group'] in ['ORG', 'ORGANIZATION']]
    if orgs:
        return list(dict.fromkeys(orgs))
    # Fallback: keyword-based
    fallback_keywords = r'\b(Pvt|Ltd|LLP|Inc|Solutions|Tech|Corp|Company|Services|Advertising|Construction|Limited|प्रा\. लि\.|सोल्यूशन्स)\b'
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    fallback_orgs = [l for l in lines if re.search(fallback_keywords, l, re.I)]
    return list(dict.fromkeys(fallback_orgs))

def extract_phones(text):
    phones = []
    text_cleaned = re.sub(r'[^\x20-\x7E]', '', text)
    raw_numbers = re.findall(r'\+?\d[\d\s\-\(\)]{6,}\d', text_cleaned)
    # print("Raw Phone Numbers Found:", raw_numbers)
    for num in raw_numbers:
        cleaned = re.sub(r'[^\d\+]', '', num)
        try:
            match = phonenumbers.parse(cleaned, "IN")
            # print("Parsed Phone Number:", match)
            if phonenumbers.is_valid_number(match):
                e164 = phonenumbers.format_number(match, phonenumbers.PhoneNumberFormat.E164)
                phones.append(e164)
        except:
            continue
        # print("Extracted Phones:", phones)
        # print("Raw Phone Strings:", raw_numbers)
    return list(set(phones)), raw_numbers 

def extract_emails(text):
    email_pattern = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:com|co\.in|in|org|net|biz|info|edu|io|gov)\b', re.I)
    emails = list(dict.fromkeys([e.strip().lower() for e in re.findall(email_pattern, text)]))
    return emails

def extract_websites(text):
    url_pattern = re.compile(r'\b(?:https?:\/\/|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\/[^\s]*)?|\b[a-zA-Z0-9.-]+\.(?:com|in|co\.in|org|net|biz|info|io|me|ai)\b', re.I)
    websites = []
    for w in re.findall(url_pattern, text):
        w = w.strip().lower().rstrip('.,;:')
        if not w.startswith("http") and not w.startswith("www."):
            w = "www." + w
        websites.append(w)
    return list(dict.fromkeys(websites))

def extract_designation(text):
    entities = ner_model(text)
    roles_ner = [ent['word'] for ent in entities if ent['entity_group'] in ['TITLE','ROLE','DESIGNATION']]
    role_keywords = [ 'manager', 'developer', 'engineer', 'designer', 'business','leading','executive', 'head', 'director', 'ceo', 'cto', 'coo', 'founder', 'owner', 'partner', 'analyst', 'consultant', 'associate', 'supervisor', 'lead', 'administrator', 'chairman', 'officer', 'president', 'co-founder', 'marketing', 'hr', 'human resource', 'business development', 'operations', 'finance', 'account', 'trainer', 'architect','leading','estate', 'व्यवस्थापक','संचालक','सहकारी','अध्यक्ष' ]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    roles_kw = [l for l in lines if any(kw in l.lower() for kw in role_keywords) and '@' not in l and 'www' not in l]
    return list(dict.fromkeys(roles_ner + roles_kw))

# Map Devanagari digits to ASCII

def extract_address(text):
    import re

    # Remove websites
    text = re.sub(r'http\S+|www\.\S+', '', text)

    lines = [l.strip().rstrip(',') for l in text.split("\n") if l.strip()]
    print("this is the lines\n", lines)

    entities = ner_model(text)
    locs = [ent['word'] for ent in entities if ent['entity_group'] in ['LOC', 'GPE']]
    print(locs)

    address_keywords = [
        'road','street','st.','opp','near','city','plot','shop','no.',
        'floor','wing','india','pincode','sector','lane','bldg',
        'nagar','block','avenue','distt','tehsil','estate',
        'centre', 'centrum', 'office',
        # Marathi address keywords
        'रोड', 'रस्ता', 'शहर', 'मोहल्ला', 'वाटा', 'पत्ता', 'गल्ला', 'प्लॉट',
        'बाजार', 'नंबर', 'माळ', 'फ्लॅट', 'मंजूर', 'वि.', 'जमीन', 'संख्या',
        # Common address starters
        'flat', 'shop', 'plot', 'colony', 'area', 'locality', 'station'
    ]

    phone_pattern = re.compile(r'\+?\d[\d\s\-\(\)]{6,}\d')
    zip_pattern = re.compile(r'\b\d{3}[\s\-]?\d{3}\b')
    exclude_patterns = re.compile(r'\b(mobile|mob|tel|phone|website|www|email|e-mail|your|formerly|formeriy|as|manager|comfort|sales|subsidiary|executive|officer|secretary|com)\b', re.I)

    block = []
    collecting = False

    for l in lines:
        lower = l.lower()

        # Skip phone numbers and irrelevant lines
        if phone_pattern.search(l) or exclude_patterns.search(lower):
            continue

        # Normalize line for ZIP detection
        line_norm = l.replace('-', ' ').strip()

        # Start collecting if line has ZIP OR looks like address (keyword, number, NER location)
        if not collecting:
            if zip_pattern.search(line_norm) or any(kw in lower for kw in address_keywords) or any(loc.lower() in lower for loc in locs) or re.search(r'\d+', l):
                collecting = True

        if collecting:
            block.append(l)

            # Stop immediately after ZIP line
            if zip_pattern.search(line_norm):
                break

    # Join lines into one address string
    address = ", ".join(block)
    # Clean repeated commas or spaces
    address = re.sub(r',\s*,+', ', ', address)
    address = re.sub(r'\s{2,}', ' ', address)

    return address.strip()



def parse_extracted_data(text):
   
    # lines = filter_meaningful_lines(text)
    phones, raw_phone_strings = extract_phones(text)
    # print("Extracted Phones:", phones)

    text = clean_ocr_text(text)
    print("Cleaned OCR Text:\n", text)


    text_no_phones = text
    for raw in raw_phone_strings:
        text_no_phones = text_no_phones.replace(raw, ' ')
    # print("Text after removing phone numbers:\n", text_no_phones)

   

    emails = extract_emails(text_no_phones)
    # print("Extracted Emails:", emails)


    text_no_phones_emails = text_no_phones
    for email in emails:
        text_no_phones_emails = text_no_phones_emails.replace(email, ' ')
    # print("Text after removing emails:\n", text_no_phones_emails)
    websites = extract_websites(text_no_phones_emails)
    # print("Extracted Websites:", websites)
    text_no_websites = text_no_phones_emails
    for site in websites:
        text_no_websites = text_no_websites.replace(site, ' ')
    # print("Text after removing websites:\n", text_no_websites)
    designation = extract_designation(text_no_websites)
    # print("Extracted Designations:", designation)
    text_no_designations = text_no_websites
    for des in designation:
        text_no_designations = text_no_designations.replace(des, ' ')
    # address = extract_address(text_no_designations)
    # print("Extracted Address:", address)
    # name = extract_name(text_no_websites)
    # company = extract_company(text_no_websites)
        
    name = extract_name(text_no_websites)
    
    print("Name:", name)
    company = extract_company(text_no_websites)


    # --- Ensure name is always a list ---
    if isinstance(name, str):
        name_list = [name]
    elif isinstance(name, list):
        name_list = name
    else:
        name_list = []

    primary_name = name_list[0] if name_list else ''

    # Clean name from text
    text_no_name = text_no_designations
    for n in name_list:
        text_no_name = text_no_name.replace(n, '')
    print("no text", text_no_name)

    address = extract_address(text_no_name)
    print("Extracted Address:", address)

    print("Company:", company)

    return {
        "name": name,
        "primary_name": name,
        "company": company,
        "primary_company": company[0] if company else '',
        "emails": emails,
        "primary_email": emails[0] if emails else '',
        "phones": phones,
        "designation": designation,
        "primary_designation": designation[0] if designation else '',
        "primary_phone": phones[0] if phones else '',
        "address": address,
        "raw_text": text
    }