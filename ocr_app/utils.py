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
ner_model_multi = pipeline( "ner", 
                           model="Davlan/xlm-roberta-large-ner-hrl",
                            aggregation_strategy="simple" )

# ----------------------------
# OCR MODEL
# ----------------------------
ocr = PaddleOCR(use_angle_cls=False, lang='mr')  # Marathi OCR
# English OCR

# ----------------------------
# OCR TEXT EXTRACTION
# ----------------------------
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
    print("Extracted Text:", text)
    return text, confidence_scores, structured_result
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
    entities = ner_model_multi(text)
    names = [ent['word'] for ent in entities if ent['entity_group'] in ['PER', 'PERSON']]
    return list(dict.fromkeys(names))

def extract_company(text):
    entities = ner_model_multi(text)
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
            print("Parsed Phone Number:", match)
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
    entities = ner_model_multi(text)
    roles_ner = [ent['word'] for ent in entities if ent['entity_group'] in ['TITLE','ROLE','DESIGNATION']]
    role_keywords = [ 'manager', 'developer', 'engineer', 'designer', 'executive', 'head', 'director', 'ceo', 'cto', 'coo', 'founder', 'owner', 'partner', 'analyst', 'consultant', 'associate', 'supervisor', 'lead', 'administrator', 'chairman', 'officer', 'president', 'co-founder', 'marketing', 'hr', 'human resource', 'business development', 'operations', 'finance', 'account', 'trainer', 'architect','leading','estate', 'व्यवस्थापक','संचालक','सहकारी','अध्यक्ष' ]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    roles_kw = [l for l in lines if any(kw in l.lower() for kw in role_keywords) and '@' not in l and 'www' not in l]
    return list(dict.fromkeys(roles_ner + roles_kw))

# ----------------------------
# INDIAN ADDRESS EXTRACTION
# ----------------------------
def extract_address(text):
    text = text.replace('\xa0', ' ').replace('\u200b', '').strip()
    lines = [l.strip().rstrip(',') for l in text.split("\n") if l.strip()]

    # Regex patterns
    phone_pattern = re.compile(r'\+?\d[\d\s\-\(\)]{6,}\d')
    pin_pattern = re.compile(r'\b\d{6}\b')  # Indian PIN
    flat_building_pattern = re.compile(r'^\s*\d+[A-Za-z0-9/\-]*[,]*.*', re.I)
    street_keywords = ['road','street','st.','lane','nagar','block','sector','bunglow','building','plot','chowk','cross','path']
    
    state_list = [
        'Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh','Goa','Gujarat','Haryana',
        'Himachal Pradesh','Jharkhand','Karnataka','Kerala','Madhya Pradesh','Maharashtra','Manipur',
        'Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan','Sikkim','Tamil Nadu','Telangana',
        'Tripura','Uttar Pradesh','Uttarakhand','West Bengal','Delhi','Jammu and Kashmir','Ladakh',
        'Puducherry','Chandigarh','Lakshadweep','Andaman and Nicobar'
    ]
    country_list = ['India','भारत']

    # Remove phone lines
    lines = [l for l in lines if not phone_pattern.fullmatch(l.replace(' ','').replace('-',''))]

    address_lines = []

    # Flat/Building number line
    for l in lines:
        if flat_building_pattern.match(l):
            address_lines.append(l)
            break

    # Street/Area lines
    for l in lines:
        if any(kw in l.lower() for kw in street_keywords) and l not in address_lines:
            address_lines.append(l)

    # City and PIN
    city_line = ''
    pin_code = ''
    for l in reversed(lines):
        pin_match = pin_pattern.search(l)
        if pin_match:
            pin_code = pin_match.group()
            city_line = l.replace(pin_code,'').strip()
            if city_line:
                address_lines.append(f"{city_line} {pin_code}")
            else:
                address_lines.append(pin_code)
            break

    # State
    for state in state_list:
        for l in lines:
            if state.lower() in l.lower() and state not in address_lines:
                address_lines.append(state)
                break

    # Country
    for country in country_list:
        for l in lines:
            if country.lower() in l.lower() and country not in address_lines:
                address_lines.append(country)
                break

    # Remove duplicates & join
    final_address = []
    for l in address_lines:
        if l and l not in final_address:
            final_address.append(l)
    print(final_address)
    return "\n".join(final_address)


# ----------------------------
# PARSE EXTRACTED DATA
# ----------------------------
def parse_extracted_data(text):
   
    # lines = filter_meaningful_lines(text)
    phones, raw_phone_strings = extract_phones(text)
    # print("Extracted Phones:", phones)

    text = clean_ocr_text(text)
    print("Cleaned OCR Text:\n", text)


    text_no_phones = text
    for raw in raw_phone_strings:
        text_no_phones = text_no_phones.replace(raw, ' ')
    print("Text after removing phone numbers:\n", text_no_phones)

   

    emails = extract_emails(text_no_phones)
    print("Extracted Emails:", emails)


    text_no_phones_emails = text_no_phones
    for email in emails:
        text_no_phones_emails = text_no_phones_emails.replace(email, ' ')
    # print("Text after removing emails:\n", text_no_phones_emails)
    websites = extract_websites(text_no_phones_emails)
    print("Extracted Websites:", websites)
    text_no_websites = text_no_phones_emails
    for site in websites:
        text_no_websites = text_no_websites.replace(site, ' ')
    print("Text after removing websites:\n", text_no_websites)
    designation = extract_designation(text_no_websites)
    print("Extracted Designations:", designation)
    text_no_designations = text_no_websites
    for des in designation:
        text_no_designations = text_no_designations.replace(des, ' ')
    address = extract_address(text_no_designations)
    print("Extracted Address:", address)
    name = extract_name(text_no_websites)
    company = extract_company(text_no_websites)

    print("Name:", name)
    print("Company:", company)

    return {
        "name": name,
        "primary_name": name[0] if name else '',
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