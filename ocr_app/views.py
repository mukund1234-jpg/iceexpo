from django.shortcuts import render, redirect
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login, authenticate , logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import BusinessCard
from .utils import extract_text, parse_extracted_data
import base64
import cv2
import numpy as np
import os
import uuid
import time
import qrcode
import pandas as pd
from django.conf import settings

from django.http import JsonResponse
# Upload and OCR Extract
# -----------------------

def preprocess_image(image_path):
    """
    Enhanced preprocessing for OCR — works better on light-print or faint text.
    """
    # Read image
    img = cv2.imread(image_path)
    if img is None:
        return None

    # Resize to consistent scale (improves OCR)
    h, w = img.shape[:2]
    if max(h, w) < 1000:
        scale = 1000 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- Step 1: Enhance contrast using CLAHE ---
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # --- Step 2: Remove noise (light smooth) ---
    denoised = cv2.fastNlMeansDenoising(enhanced, None, 15, 7, 21)

    # --- Step 3: Adaptive Threshold with Otsu + Inversion ---
    # (Helps faint dark text on light backgrounds)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,  # invert for light text
        31, 15
    )

    # --- Step 4: Morphological cleanup (open small noise) ---
    kernel = np.ones((2, 2), np.uint8)
    morph = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # --- Step 5: Combine with original for fine details ---
    processed = cv2.bitwise_or(morph, 255 - denoised)

    # --- Step 6: Optional sharpening ---
    sharpen_kernel = np.array([[0, -1, 0],
                               [-1, 5, -1],
                               [0, -1, 0]])
    sharp = cv2.filter2D(processed, -1, sharpen_kernel)

    # --- Step 7: Save processed image ---
    fs = FileSystemStorage()
    base_name = os.path.basename(image_path)
    filename = f"preprocessed_{base_name}"

    success, encoded_img = cv2.imencode('.jpg', sharp)
    if not success:
        return None

    saved_path = fs.save(filename, ContentFile(encoded_img.tobytes()))
    return fs.path(saved_path)
import requests


@csrf_exempt
def upload_card(request):
    total_users = 0
    if request.method == 'POST':
        fs = FileSystemStorage()
        if request.POST.get('webcam_image'):
            _, imgstr = request.POST['webcam_image'].split(';base64,')
            image_bytes = base64.b64decode(imgstr)
            unique_filename = f"webcam_{uuid.uuid4().hex}.jpg"
            image_path = fs.save(unique_filename, ContentFile(image_bytes))
            image_path = fs.path(image_path)
        else:
            messages.error(request, "No image provided")
            return redirect('new_registration')

        start_time = time.time()

        # (Optional preprocessing)
        # preprocessed_path = preprocess_image(image_path)

        # Extract text via OCR
        text = extract_text(image_path)
        ocr_time = time.time()
        print(f"OCR Extraction Time: {ocr_time - start_time:.2f} seconds")
       

        # Parse structured data (phones, emails, etc.)
        data = parse_extracted_data(text)
        parse_time = time.time()
        print(f"Data Parsing Time: {parse_time - ocr_time:.2f} seconds")

        total_time = parse_time - start_time
        print(f"Total Processing Time: {total_time:.2f} seconds")

        text_lines = [line.strip() for line in text.split('\n') if line.strip()]


        excel_file = os.path.join(settings.MEDIA_ROOT, 'business_cards.xlsx')
        if os.path.exists(excel_file):
            df_existing = pd.read_excel(excel_file)
            total_users = len(df_existing)
        else:
            total_users = 0
        print(f"Total users before registration: {total_users}")

        return render(request, 'ocr/register_card.html', {
            'name': data.get('name', ''),
            'primary_name': data.get('primary_name', ''),
            'text_lines': text_lines,
            'emails': data.get('emails', []),
            'primary_email': data.get('primary_email', ''),
            'phones': data.get('phones', []),
            'primary_phone': data.get('primary_phone', ''),
            'designation': data.get('designation', ''),
            'primary_designation': data.get('primary_designation', ''),
            'company': data.get('company', ''),
            'primary_company': data.get('primary_company', ''),
            'address': data.get('address', ''),
            'processing_time': f"{total_time:.2f} seconds",
            'total': total_users 
        })
    excel_file = os.path.join(settings.MEDIA_ROOT, 'business_cards.xlsx')
    if os.path.exists(excel_file):
        total_users = len(pd.read_excel(excel_file))
    return render(request, 'ocr/register_card.html', {'total': total_users})



@csrf_exempt
def register_card(request):
    # 📁 Paths
    excel_file = os.path.join(settings.MEDIA_ROOT, 'business_cards.xlsx')
    qr_folder = os.path.join(settings.MEDIA_ROOT, 'qr_codes')
    os.makedirs(qr_folder, exist_ok=True)

    # 🧾 Load existing Excel or create new
    if os.path.exists(excel_file):
        df_existing = pd.read_excel(excel_file)
        df_existing.columns = df_existing.columns.str.strip()
        df_existing.rename(columns={'QR Code': 'QR_Code'}, inplace=True)
    else:
        df_existing = pd.DataFrame(columns=[
            'UID', 'Name', 'Email', 'Phone', 'Company', 
            'Designation', 'Category', 'Address', 'QR_Code'
        ])
        df_existing.to_excel(excel_file, index=False)

    # 🔢 Get total user count
    total_users = len(df_existing)

    if request.method == 'POST':

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        designation = request.POST.get('designation', '').strip()
        category = request.POST.get('category', '').strip()
        company = request.POST.get('company', '').strip()
        address = request.POST.get('address', '').strip()

        uid = str(uuid.uuid4().hex[:6]).upper()

        # 🧾 Create QR content
        qr_data = (
            f" {uid}\n"
            f"{name}\n {email}\n {phone}\n"
            f" {designation}\n {category}\n"
            f" {company}\n {address}"
        )
        qr_filename = f"{uid}_QR.png"
        qr_path = os.path.join(qr_folder, qr_filename)
        qrcode.make(qr_data).save(qr_path)

        # 🆕 Add new entry
        new_row = pd.DataFrame([{
            'UID': uid,
            'Name': name,
            'Email': email,
            'Phone': phone,
            'Designation': designation,
            'Category': category,
            'Company': company,
            'Address': address,
            'QR_Code': f"qr_codes/{qr_filename}"
        }])

        df_existing = pd.concat([df_existing, new_row], ignore_index=True)
        df_existing.to_excel(excel_file, index=False)

        total_users = len(df_existing)

        # 📤 Pass data to template
        user = {
            'UID': uid,
            'Name': name,
            'Email': email,
            'Phone': phone,
            'Designation': designation,
            'Category': category,
            'Company': company,
            'Address': address,
            'QR_URL': f"{settings.MEDIA_URL}qr_codes/{qr_filename}",
        }

        return render(request, 'ocr/pass.html', {'user': user, 'total': total_users})

    return render(request, 'ocr/register_card.html', {'total': total_users})
def main_page(request):
    return render(request, 'ocr/main_page.html')



