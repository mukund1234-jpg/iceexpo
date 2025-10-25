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
# -----------------------
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

@csrf_exempt
def upload_card(request):
    if request.method == 'POST':
        fs = FileSystemStorage()
        if request.FILES.get('up_image'):
            img = request.FILES['up_image']
            filename = fs.save(img.name, img)
            image_path = fs.path(filename)
            
        elif request.POST.get('webcam_image'):
            _, imgstr = request.POST['webcam_image'].split(';base64,')
            image_bytes = base64.b64decode(imgstr)
            filename = 'webcam_card.jpg'
            image_path = fs.save(filename, ContentFile(image_bytes))
            image_path = fs.path(image_path)
        else:
            messages.error(request, "No image provided")
            return redirect('new_registration')
        # preprocessed_path = preprocess_image(image_path)

        text= extract_text(image_path)
        data = parse_extracted_data(text)
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Check if card already exists
        existing_card = None
        email = data.get('primary_email', '').strip()
        phone = data.get('primary_phone', '').strip()
        name = data.get('name', '')
        pr = data.get('primary_name', '')
        print(name)
        print("this is the primary name\n",pr)
        if email:
            existing_card = BusinessCard.objects.filter(email=email).first()
        if not existing_card and phone:
            existing_card = BusinessCard.objects.filter(phone=phone).first()

        if existing_card:
            messages.warning(request, "User already exists. Please log in.")
            return redirect('already_registered')
        
        return render(request, 'ocr/register_card.html', {
            'image_url': fs.url(filename),
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
        })

    return render(request, 'ocr/register_card.html')

# -----------------------
# Register Card / User
# -----------------------
@csrf_exempt
def register_card(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        company = request.POST.get('company', '').strip()
        address = request.POST.get('address', '').strip()
        image_file = request.FILES.get('image')

        # Check if card/user already exists
        existing_card = None
        if email:
            existing_card = BusinessCard.objects.filter(email=email).first()
        if not existing_card and phone:
            existing_card = BusinessCard.objects.filter(phone=phone).first()

        if existing_card:
            messages.info(request, "User already registered. Please log in.")
            return redirect('already_registered')

        # Create BusinessCard as user
        card = BusinessCard.objects.create_user(
            email=email if email else None,
            phone=phone if phone else None,
            password=phone,  # Default password is phone
            name=name,
            company=company,
            address=address,
            image=image_file
        )

        login(request, card)
        messages.success(request, f"Registered Successfully as {card.name}")
        return redirect('profile_page')

    return redirect('new_registration')

# -----------------------
# Login via OCR / Image
# -----------------------
@csrf_exempt
def login_card(request):
    if request.method == 'POST':
        fs = FileSystemStorage()
        if request.POST.get('webcam_image'):
            _, imgstr = request.POST['webcam_image'].split(';base64,')
            image_bytes = base64.b64decode(imgstr)
            filename = 'login_card.jpg'
            image_path = fs.save(filename, ContentFile(image_bytes))
            image_path = fs.path(image_path)
        elif request.FILES.get('card_image'):
            img = request.FILES['card_image']
            filename = fs.save(img.name, img)
            image_path = fs.path(filename)
        else:
            messages.error(request, "No image provided")
            return redirect('new_registration')

        text = extract_text(image_path)
        data = parse_extracted_data(text)
        email = data.get('primary_email', '').strip()
        phone = data.get('primary_phone', '').strip()

        # Authenticate by email or phone
        card = None
        if email:
            card = BusinessCard.objects.filter(email=email).first()
        if not card and phone:
            card = BusinessCard.objects.filter(phone=phone).first()

        if not card:
            messages.error(request, "User not registered. Please register first.")
            return redirect('new_registration')

        # Log in
        login(request, card)
        messages.success(request, f"Logged in as {card.name}")
        return redirect('profile_page')

    return render(request, 'ocr/login_card.html')

# -----------------------
# Login via identifier (email/phone)
# -----------------------
@csrf_exempt
def login_after_card(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()
        if not identifier:
            messages.error(request, "Please enter your Email or Phone number.")
            return redirect('login_after_card')

        email = identifier if '@' in identifier else None
        phone = None
        if not email:
            phone_clean = identifier.replace(" ", "").replace("-", "")
            if phone_clean.startswith('+') or phone_clean.isdigit():
                phone = '+91' + phone_clean if len(phone_clean) == 10 else phone_clean

        card = None
        if email:
            card = BusinessCard.objects.filter(email=email).first()
        elif phone:
            card = BusinessCard.objects.filter(phone=phone).first()

        if not card:
            messages.error(request, "User not registered. Please register first.")
            return redirect('new_registration')

        login(request, card)
        messages.success(request, f"Logged in successfully as {card.name}")
        return redirect('profile_page')

    return render(request, 'ocr/login_after_card.html')

# -----------------------
# Main page
# -----------------------
def main_page(request):
    return render(request, 'ocr/main_page.html')

# -----------------------
# Profile page
# -----------------------
@login_required
def profile(request):
    card = request.user  # BusinessCard is the user now
    return render(request, 'ocr/profile.html', {'card': card})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('already_registered')