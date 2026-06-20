from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Customer, Transaction
import base64
from django.utils.dateparse import parse_date
from django.db.models import Q
from django.utils import timezone
import urllib.parse
# khata/views.py ke sabse upar jodein
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.http import HttpResponse
from .models import ShopProfile


@login_required
def dashboard(request):
    # Error aane par app crash hone se rokne ke liye try block (Error Handling)
    try:
        # Base list: User ke saare grahak
        customers = Customer.objects.filter(user=request.user).order_by('name')
        
        # URL se 'search' aur 'filter' parameters nikalna
        search_query = request.GET.get('search', '').strip()
        filter_type = request.GET.get('filter', 'all')
        
        # Search Logic: Agar user ne kuch type kiya hai, toh filter lagayein
        if search_query:
            # Q object ka use karke Naam (name) YA Phone (phone) dono me search karna (icontains = case-insensitive match)
            customers = customers.filter(
                Q(name__icontains=search_query) | Q(phone__icontains=search_query)
            ).order_by('name')
        
        total_lene_hain = 0  
        total_dene_hain = 0  
        filtered_customers = []
        
        # Har grahak ka balance nikalna aur status ke hisaab se filter karna
        for customer in customers:
            transactions = Transaction.objects.filter(customer=customer)
            
            given = sum(t.amount for t in transactions if t.trans_type == 'GIVEN')
            got = sum(t.amount for t in transactions if t.trans_type == 'GOT')
            
            net_balance = given - got
            
            # Sirf overall dashboard ke calculation ke liye
            if net_balance > 0:
                total_lene_hain += net_balance
            elif net_balance < 0:
                total_dene_hain += abs(net_balance)
                
            # Grahak ke object me balance set karna
            customer.balance = net_balance
            customer.abs_balance = abs(net_balance) 
            
            # Cards wale Filter Logic
            if filter_type == 'lene' and net_balance <= 0:
                continue 
            if filter_type == 'dene' and net_balance >= 0:
                continue 
                
            # filtered_customers.append(customer)
            # Grahak ki ID ko Base64 me encode karna taaki URL secure rahe
            customer.b64_id = base64.b64encode(str(customer.id).encode('utf-8')).decode('utf-8')
            
            filtered_customers.append(customer)
        context = {
            'customers': filtered_customers, 
            'total_lene_hain': total_lene_hain,
            'total_dene_hain': total_dene_hain,
            'current_filter': filter_type,
            'search_query': search_query, # Template me search text wapas dikhane ke liye
        }
        return render(request, 'khata/dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f"Dashboard load karne me error aayi: {str(e)}")
        return render(request, 'khata/error.html')
    

@login_required
def add_customer(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            phone = request.POST.get('phone')
            
            # Duplicate Check: Check karein ki is user ne is phone number se pehle hi customer add toh nahi kiya
            if Customer.objects.filter(user=request.user, phone=phone).exists():
                messages.warning(request, "Yeh number pehle se hi list me maujood hai!")
                return redirect('dashboard')
            
            # Agar duplicate nahi hai, toh naya customer save karein
            new_customer = Customer(user=request.user, name=name, phone=phone)
            new_customer.save()
            messages.success(request, "Naya grahak safaltapoorvak add ho gaya!")
            return redirect('dashboard')
            
        except Exception as e:
            # Error aane par handle karein
            messages.error(request, f"Grahak jodne me samasya: {str(e)}")
            return redirect('dashboard')
            
    return render(request, 'khata/add_customer.html')


@login_required
def edit_customer(request, b64_id):
    # Error Handling: Code me koi problem aaye to app crash na ho
    try:
        # Base64 decode karke actual ID nikalna
        actual_id = int(base64.b64decode(b64_id).decode('utf-8'))
        customer = get_object_or_404(Customer, id=actual_id, user=request.user)

        if request.method == 'POST':
            name = request.POST.get('name')
            phone = request.POST.get('phone')

            # Duplicate Check: Kahi ye naya phone number kisi doosre grahak ka to nahi?
            # exclude() ka use isliye kiya taaki khud ke current number ko duplicate na maane
            if Customer.objects.filter(user=request.user, phone=phone).exclude(id=customer.id).exists():
                messages.warning(request, "Yeh phone number pehle se hi kisi aur grahak ke naam par darj hai! (Duplicate Error)")
                return redirect('edit_customer', b64_id=b64_id)

            # Details update karke save karna
            customer.name = name
            customer.phone = phone
            customer.save()
            messages.success(request, "Grahak ki jankari safaltapoorvak update ho gayi!")
            return redirect('dashboard')

        # GET request aane par edit form dikhana
        context = {
            'customer': customer,
            'b64_id': b64_id
        }
        return render(request, 'khata/edit_customer.html', context)

    except Exception as e:
        # Error aane par wapas dashboard bhejna
        messages.error(request, f"Grahak edit karne me error aayi: {str(e)}")
        return redirect('dashboard')

@login_required
def delete_customer(request, customer_id):
    # Error Handling ke liye try block (App crash hone se rokne ke liye)
    try:
        # Check karna ki grahak isi user ka hai ya nahi
        customer = get_object_or_404(Customer, id=customer_id, user=request.user)
        
        # Pehle grahak ke saare len-den (transactions) nikalna balance check karne ke liye
        transactions = Transaction.objects.filter(customer=customer)
        
        total_given = sum(t.amount for t in transactions if t.trans_type == 'GIVEN')
        total_got = sum(t.amount for t in transactions if t.trans_type == 'GOT')
        net_balance = total_given - total_got
        
        # PRE-CHECK LOGIC: Agar balance 0 nahi hai (yani lena ya dena baki hai)
        if net_balance != 0:
            # SweetAlert is warning ko automatically pakad lega aur dikha dega
            messages.warning(
                request, 
                f"Is Customers ko delete nahi kiya ja sakta! Abhi ₹{abs(net_balance):.2f} ka hisaab baki hai."
            )
            return redirect('dashboard')
            
        # Agar balance ekdum 0 hai, tabhi delete ki ijazat milegi
        customer.delete()
        messages.success(request, "Grahak ka khata safaltapoorvak hata diya gaya hai.")
        return redirect('dashboard')
        
    except Exception as e:
        # Kisi bhi unexpected dikkat ko handle karne ke liye
        messages.error(request, f"Grahak hatane mein error aayi: {str(e)}")
        return redirect('dashboard')


@login_required
def customer_detail(request, customer_id):
    # Error Handling ke liye try block
    try:
        customer = get_object_or_404(Customer, id=customer_id, user=request.user)
        
        if request.method == 'POST':
            amount = request.POST.get('amount')
            trans_type = request.POST.get('trans_type')
            remarks = request.POST.get('remarks')
            date_str = request.POST.get('date') # Form se tareekh nikalna
            
            trans_date = parse_date(date_str)
            
            # Duplicate Check: Agar same grahak ka, same date pe, same amount ka same type ka len-den hai
            if Transaction.objects.filter(customer=customer, amount=amount, trans_type=trans_type, date=trans_date).exists():
                messages.warning(request, "Aisi same entry is tareekh par pehle se maujood hai! (Duplicate Error)")
                return redirect('customer_detail', customer_id=customer_id)

            new_trans = Transaction(
                customer=customer,
                amount=amount,
                trans_type=trans_type,
                remarks=remarks,
                date=trans_date
            )
            new_trans.save()
            messages.success(request, "Len-den ka hisaab kamyabi se jod diya gaya!")
            return redirect('customer_detail', customer_id=customer_id)

        # Auto Arrange Date wise: '-date' likhne se sabse nayi tareekh upar aayegi
        transactions = Transaction.objects.filter(customer=customer).order_by('date', 'id')
        
        total_given = sum(t.amount for t in transactions if t.trans_type == 'GIVEN')
        total_got = sum(t.amount for t in transactions if t.trans_type == 'GOT')
        net_balance = total_given - total_got

       # ---> NAYA LOGIC (UPDATED WITH FIX) <---
        auto_months = 0
        # Agar koi transaction mojood hai, toh sabse aakhri date nikalenge
        if transactions.exists():
            last_trans = transactions.last() 
            
            # FIX: Purani entries (datetime) ko sirf 'date' mein badalne ka logic
            last_date = last_trans.date
            if hasattr(last_date, 'date'):  # Agar isme samay (time) bhi juda hai
                last_date = last_date.date()  # Toh usme se sirf tareekh nikal lo
            
            # Aaj ki tareekh aur aakhri len-den ke beech kitne din nikle?
            # Ab dono taraf sirf 'date' format hai, toh error nahi aayegi
            days_passed = (timezone.now().date() - last_date).days
            
            if days_passed > 0:
                # 30 din ko ek mahina mankar divide kiya, 1 decimal place tak round kiya
                auto_months = round(days_passed / 30.0, 1)
        # ---> NAYA LOGIC YAHAN KHATAM <---

            # Security ke liye har transaction ki ID ko Base64 me encode karke template me bhejenge
            running_balance = 0 # Balance shuruat se 0 rakhein
            for t in transactions:
                t.b64_id = base64.b64encode(str(t.id).encode('utf-8')).decode('utf-8')
                
                # Balance Calculation
                if t.trans_type == 'GIVEN':
                    running_balance += t.amount
                else:
                    running_balance -= t.amount
                
                t.running_balance = running_balance # Har row ke liye current balance set kiya

        # ---> WHATSAPP REMINDER LOGIC SHURU <---
        whatsapp_url = ""
        # Agar udhaar (net_balance) 0 se zyada hai, tabhi reminder link banega
        if net_balance > 0:
            # Grahak ke liye ek badhiya sa message banayein
            message = f"नमस्ते  {customer.name} जी,\nआपका बकाया उधार ₹{net_balance:.2f} बाकी है, कृपया समय पर भुगतान करे.\nधन्यवाद!\nदिलीप डेलवास"
            
            # Message ko URL format me encode karna zaroori hai (jaise space ki jagah %20 ho jana)
            encoded_message = urllib.parse.quote(message)
            
            # Phone number filter karna (sirf numbers rakhna)
            phone_number = ''.join(filter(str.isdigit, customer.phone))
            
            # Agar number 10 digit ka hai aur aage 91 nahi laga, toh 91 jod dein (India code)
            if len(phone_number) == 10:
                phone_number = "91" + phone_number
                
            # Final WhatsApp API URL
            whatsapp_url = f"https://wa.me/{phone_number}?text={encoded_message}"
        # ---> WHATSAPP LOGIC KHATAM <---
            
        encoded_id = base64.b64encode(str(customer.id).encode('utf-8')).decode('utf-8')
        
        # Security ke liye har transaction ki ID ko Base64 me encode karke template me bhejenge
        for t in transactions:
            t.b64_id = base64.b64encode(str(t.id).encode('utf-8')).decode('utf-8')
        
        context = {
            'customer': customer,
            'transactions': transactions,
            'net_balance': net_balance,
            'encoded_id': encoded_id,
            'auto_months': auto_months,
            'whatsapp_url': whatsapp_url,
        }
        return render(request, 'khata/customer_detail.html', context)
        
    except Exception as e:
        messages.error(request, f"Hisaab kholne mein samasya aayi: {str(e)}")
        return redirect('dashboard')

@login_required
def edit_transaction(request, b64_trans_id):
    # Error Handling lagaya gaya hai
    try:
        actual_trans_id = int(base64.b64decode(b64_trans_id).decode('utf-8'))
        trans = get_object_or_404(Transaction, id=actual_trans_id, customer__user=request.user)

        if request.method == 'POST':
            amount = request.POST.get('amount')
            trans_type = request.POST.get('trans_type')
            remarks = request.POST.get('remarks')
            date_str = request.POST.get('date')
            trans_date = parse_date(date_str)

            # Duplicate Check: Existing entry ko chhod kar baaki check karna
            if Transaction.objects.filter(
                customer=trans.customer, amount=amount, trans_type=trans_type, date=trans_date
            ).exclude(id=trans.id).exists():
                messages.warning(request, "Same aisi len-den ki entry pehle se maujood hai!")
                return redirect('edit_transaction', b64_trans_id=b64_trans_id)

            # Entry update karna
            trans.amount = amount
            trans.trans_type = trans_type
            trans.remarks = remarks
            trans.date = trans_date
            trans.save()
            
            messages.success(request, "Len-den ki entry update ho gayi!")
            return redirect('customer_detail', customer_id=trans.customer.id)

        # GET method ke liye Date ko HTML (YYYY-MM-DD) format me convert karna
        date_formatted = trans.date.strftime('%Y-%m-%d') if trans.date else ''

        context = {
            'trans': trans,
            'customer': trans.customer,
            'b64_trans_id': b64_trans_id,
            'date_formatted': date_formatted
        }
        return render(request, 'khata/edit_transaction.html', context)

    except Exception as e:
        messages.error(request, f"Entry edit karne me samasya: {str(e)}")
        return redirect('dashboard')

@login_required
def delete_transaction(request, b64_trans_id):
    # Try block error aane se rokne ke liye
    try:
        # Base64 string ko decode karke actual transaction ID nikalna
        actual_trans_id = int(base64.b64decode(b64_trans_id).decode('utf-8'))
        
        # Check karein ki ye transaction isi user ke customer ka hai
        trans = get_object_or_404(Transaction, id=actual_trans_id, customer__user=request.user)
        customer_id = trans.customer.id
        
        trans.delete()
        messages.success(request, "Len-den ki entry delete kar di gayi hai.")
        return redirect('customer_detail', customer_id=customer_id)
        
    except Exception as e:
        messages.error(request, f"Entry delete karne mein samasya: {str(e)}")
        return redirect('dashboard')
    

@login_required
def add_interest(request, b64_id):
    # Error Handling ke liye try block (On Error GoTo logic)
    try:
        # Base64 string se actual customer ID decode karna
        actual_id = int(base64.b64decode(b64_id).decode('utf-8'))
        customer = get_object_or_404(Customer, id=actual_id, user=request.user)

        if request.method == 'POST':
            interest_amount = request.POST.get('interest_amount')
            rate = request.POST.get('rate')
            months = request.POST.get('months')
            date_str = request.POST.get('date')
            
            trans_date = parse_date(date_str)
            
            # Custom remarks banayein taaki samajh aaye ki ye entry Byaaj ki hai
            remarks = f"Byaaj (Interest): {rate}% dar se {months} mahine ka"

            # Duplicate Check: Check karein ki same date pe same Byaaj pehle toh nahi joda gaya
            if Transaction.objects.filter(customer=customer, amount=interest_amount, trans_type='GIVEN', date=trans_date, remarks=remarks).exists():
                messages.warning(request, "Byaaj ki yeh entry is tareekh par pehle se lag chuki hai! (Duplicate Error)")
                return redirect('customer_detail', customer_id=customer.id)

            # Agar duplicate nahi hai, toh nayi entry save karein
            new_trans = Transaction(
                customer=customer,
                amount=interest_amount,
                trans_type='GIVEN',  # Byaaj udhaar mein judta hai, isliye 'GIVEN'
                remarks=remarks,
                date=trans_date
            )
            new_trans.save()
            messages.success(request, f"₹{interest_amount} ka Byaaj khate mein safaltapoorvak jod diya gaya!")
            
        return redirect('customer_detail', customer_id=customer.id)
        
    except Exception as e:
        # Error aane par handle karein aur dashboard par wapas bhej dein
        messages.error(request, f"Byaaj jodne mein samasya aayi: {str(e)}")
        return redirect('dashboard')
    
@login_required
def download_ledger_pdf(request, b64_id):
    # Error aane par program crash hone se bachane ke liye try block
    try:
        # Base64 string se actual ID nikalne ke liye DecodeBase64 ka logic
        decoded_id_str = base64.b64decode(b64_id).decode('utf-8')
        actual_customer_id = int(decoded_id_str)
        
        # Grahak aur uski saari transactions fetch karein
        customer = get_object_or_404(Customer, id=actual_customer_id, user=request.user)
        transactions = Transaction.objects.filter(customer=customer).order_by('date')
        
        # Totals calculate karein
        total_given = sum(t.amount for t in transactions if t.trans_type == 'GIVEN')
        total_got = sum(t.amount for t in transactions if t.trans_type == 'GOT')
        net_balance = total_given - total_got
        
        # Template ko data pass karne ke liye context banayein
        context = {
            'customer': customer,
            'transactions': transactions,
            'net_balance': net_balance,
            'total_given': total_given,
            'total_got': total_got,
        }
        
        # PDF template load karein
        template_path = 'khata/pdf_template.html'
        template = get_template(template_path)
        html = template.render(context)
        
        # HTTP response ko PDF format ke liye set karein
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Hisaab_{customer.name}.pdf"'
        
        # HTML se PDF banayein
        pisa_status = pisa.CreatePDF(html, dest=response)
        
        if pisa_status.err:
            messages.error(request, "PDF generate karne mein error aayi.")
            return redirect('customer_detail', customer_id=customer.id)
            
        return response
        
    except Exception as e:
        # Koi bhi unexpected error handle karein
        messages.error(request, f"PDF report nikalne me samasya: {str(e)}")
        return redirect('dashboard')
    
# khata/views.py ke aakhir me ye view jodein
from .models import ShopProfile

@login_required
def shop_profile(request):
    # Error Handling start: Code me koi gadbad ho to app safe rahe
    try:
        # Existence Check: User ka profile nikalna, nahi hai toh naya bana dena
        profile, created = ShopProfile.objects.get_or_create(user=request.user)

        if request.method == 'POST':
            shop_name = request.POST.get('shop_name')
            address = request.POST.get('address')
            phone = request.POST.get('phone')

            # Data update karke save karna
            profile.shop_name = shop_name
            profile.address = address
            profile.phone = phone
            profile.save()
            
            messages.success(request, "Dukaan ka profile safaltapoorvak update ho gaya!")
            return redirect('dashboard')

        context = {
            'profile': profile
        }
        return render(request, 'khata/shop_profile.html', context)

    except Exception as e:
        # Kuch dikkat aane par error message show karein
        messages.error(request, f"Profile kholne mein samasya aayi: {str(e)}")
        return redirect('dashboard')