from django.db.models import Sum, Avg, Q, F, Value, ExpressionWrapper, DecimalField
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, ForgotPassword
from django.contrib.auth.forms import SetPasswordForm
from django.views.decorators.http import require_POST
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from main import settings
from . import models
import pycountry
import hashlib


def navbar_view(request):
    categories = models.Category.objects.all()

    # Optional: Add product count to each category
    for category in categories:
        category.product_count = category.product_set.count()

    from django.utils.text import slugify
    import math

    icon_mapping = {
        "electronics": "laptop",
        "clothing": "bag",
        "books": "book",
        "home": "house",
        # Add more mappings as needed
    }

    for category in categories:
        slug = slugify(category.name.lower())
        category.icon = icon_mapping.get(slug, "tag")

    featured_categories = categories.filter(featured=True)[:5]

    avatar_color = get_color(request.user.username)

    chunk_size = math.ceil(len(categories) / 4)  # 4 columns
    category_chunks = [
        categories[i : i + chunk_size] for i in range(0, len(categories), chunk_size)
    ]

    context = {
        "category_chunks": category_chunks,
        "featured_categories": featured_categories,
        "avatar_color": avatar_color,
    }

    return render(request, "header.html", context)


def home(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user = User.objects.get(email=email)
            if user.check_password(password):
                login(request, user)
                return redirect("store_home")
            else:
                messages.error(request, "Incorrect password.", extra_tags="login-msg")
        except User.DoesNotExist:
            messages.error(request, "User does not exist.", extra_tags="login-msg")

        return redirect("login-page")

    products = models.Product.objects.all()[:21]

    for product in products:
        product.price_display = product.price_in_peso

    wishlist_product_ids = []
    subscribed = []
    address = []
    if request.user.is_authenticated:
        wishlist_product_ids = models.ProductWishlist.objects.filter(
            user=request.user
        ).values_list("product_id", flat=True)
        subscribed = models.Subscriber.objects.filter(email=request.user.email)
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass
    return render(
        request,
        "store/home.html",
        {
            "products": products,
            "wishlist_product_ids": wishlist_product_ids,
            "subscribed": subscribed,
            "user_address": address,
        },
    )


def about_view(request):
    address = None
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass
    return render(request, "store/about.html", {"user_address": address})


@login_required(login_url="/login")
def contact_view(request):
    address = None
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass
    return render(request, "store/contact.html", {"user_address": address})


def get_color(username):
    colors = ["primary", "success", "danger", "warning", "info", "secondary"]
    hash_val = int(hashlib.md5(username.encode()).hexdigest(), 16)
    return colors[hash_val % len(colors)]


# def login_user(request):
#     if request.method == "POST":
#         username = request.POST.get("username", "").strip()
#         password = request.POST.get("password", "")
#         context = {"username": username}

#         if not username or not password:
#             messages.error(request, "Both fields are required.", extra_tags="login-msg")
#             return render(request, "store/authentication-page/login_page.html", context)

#         if not User.objects.filter(username=username).exists():
#             messages.error(request, "User does not exist.", extra_tags="login-msg")
#             return render(request, "store/authentication-page/login_page.html", context)

#         user = authenticate(request, username=username, password=password)
#         if user:
#             login(request, user)
#             return redirect("store_home")
#         else:
#             messages.error(request, "Incorrect password.", extra_tags="login-msg")
#             return render(request, "store/authentication-page/login_page.html", context)

#     return render(
#         request, "store/authentication-page/login_page.html", {"hide_login_modal": True}
#     )

from django.contrib.auth.forms import AuthenticationForm

def login_user(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect("store_home")
    else:
        form = AuthenticationForm()
    return render(request, 
                  "store/authentication-page/login_page.html", 
                  {"form": form, "hide_login_modal": True})


def register_user(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login-page")
    else:
        form = CustomUserCreationForm()

    return render(
        request,
        "store/authentication-page/register_page.html",
        {"form": form, "hide_login_modal": True},
    )


def logout_view(request):
    logout(request)
    return redirect("store_home")


def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")

        try:
            user = User.objects.get(email__iexact=email)

            new_password_reset = models.PasswordReset(user=user)
            new_password_reset.save()

            password_reset_url = reverse(
                "reset-password", kwargs={"reset_id": str(new_password_reset.reset_id)}
            )
            full_password_reset_url = (
                f"{request.scheme}://{request.get_host()}{password_reset_url}"
            )

            email_body = render_to_string(
                "store/emails/password_reset_email.html", {"reset_url": full_password_reset_url}
            )

            email_message = EmailMessage(
                "Reset your password",
                email_body,
                f"ShopNow <{settings.EMAIL_HOST_USER}>",
                [email],  # Receiver's email
            )

            email_message.content_subtype = "html"

            email_message.send(fail_silently=False)

            return redirect("password-reset-sent", reset_id=new_password_reset.reset_id)

        except User.DoesNotExist:
            messages.error(
                request,
                f"No user with email '{email}' found",
                extra_tags="forgot-pass-msg",
            )
            return redirect("forgot-password")
        except Exception as e:
            # Catch other errors (e.g., email failure)
            messages.error(
                request, f"An error occurred: {str(e)}", extra_tags="forgot-pass-msg"
            )
            return redirect("forgot-password")

    return render(
        request,
        "store/authentication-page/reset-password/forgot-password.html",
        {"hide_login_modal": True},
    )


def password_reset_sent(request, reset_id):

    if models.PasswordReset.objects.filter(reset_id=reset_id).exists():
        return render(
            request, "store/authentication-page/reset-password/password-reset-sent.html"
        )
    else:
        messages.error(request, f"Invalid reset id", extra_tags="forgot-pass-msg")
        return redirect("forgot-password")


def reset_password(request, reset_id):
    try:
        reset_entry = models.PasswordReset.objects.get(reset_id=reset_id)

        if request.method == "POST":
            password1 = request.POST.get("new_password1")
            password2 = request.POST.get("new_password2")

            password_have_error = False

            if password1 != password2:
                password_have_error = True
                messages.error(
                    request, f"Password does not match", extra_tags="reset-pass-msg"
                )
            if len(password1) < 8:
                password_have_error = True
                messages.error(
                    request,
                    f"Password must atleast 8 characters",
                    extra_tags="reset-pass-msg",
                )

            expiration_time = reset_entry.created_when + timezone.timedelta(minutes=10)
            if timezone.now() > expiration_time:
                password_have_error = True
                reset_entry.delete()
                messages.error(
                    request, f"Reset Link has expired", extra_tags="reset-pass-msg"
                )

            if not password_have_error:
                user = reset_entry.user
                user.set_password(password1)
                user.save()
                reset_entry.delete()

                messages.success(
                    request, f"Password successfully reset", extra_tags="reset-pass-msg"
                )
                return redirect("login-page")
            else:
                return redirect("reset-password", reset_id=str(reset_entry.reset_id))

    except models.PasswordReset.DoesNotExist:
        messages.error(request, f"Invalid reset id", extra_tags="reset-pass-msg")
        return redirect("forgot-password")

    return render(
        request,
        "store/authentication-page/reset-password/reset-password.html",
        {"reset_id": str(reset_entry.reset_id)},
        {"hide_login_modal": True},
    )


@login_required(login_url="/login")
def change_password_view(request):
    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        user = request.user
        if user.check_password(current_password):

            password_have_error = False

            if new_password != confirm_password:
                password_have_error = True
                messages.error(
                    request, f"Password does not match", extra_tags="change-pass-msg"
                )
            if len(new_password) < 8:
                password_have_error = True
                messages.error(
                    request,
                    f"Password must atleast 8 characters",
                    extra_tags="change-pass-msg",
                )

            if not password_have_error:
                user.set_password(new_password)
                user.save()
                login(request, user)
                return redirect("profile-page")
        else:
            messages.error(request, "Incorrect password.", extra_tags="change-pass-msg")

    return render(
        request,
        "store/authentication-page/reset-password/change-password.html",
    )


@login_required(login_url="/login")
def profile_view(request):
    user_address, created = models.ShippingAddress.objects.get_or_create(
        user=request.user
    )
    try:
        orders = models.Order.objects.filter(user=request.user)
        product_reviews = models.ProductReview.objects.filter(user=request.user)
        wishlist = models.ProductWishlist.objects.filter(user=request.user)
    except models.Order.DoesNotExist:
        orders = None

    return render(
        request,
        "store/profile-page.html",
        {
            "user_address": user_address,
            "orders": orders,
            "product_reviews": product_reviews,
            "wishlist": wishlist,
        },
    )


@login_required(login_url="/login")
def edit_profile_view(request):
    user_address, created = models.ShippingAddress.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        user_address.full_name = request.POST.get("full_name")
        user_address.phone = request.POST.get("phone")
        user_address.address = request.POST.get("address")
        user_address.postal_code = request.POST.get("postal_code")
        user_address.country = request.POST.get("country")

        profile = request.FILES.get("profile_picture")
        if profile:
            user_address.user_profile = profile

        user_address.save()
        return redirect("profile-page")

    complete_countries = sorted(
        [(c.alpha_2, c.name) for c in pycountry.countries], key=lambda x: x[1]
    )

    context = {"user_address": user_address, "countries": complete_countries}

    return render(request, "store/edit-profile-page.html", context)


def product_view(request, category=None):
    products = models.Product.objects.all()
    categories = models.Category.objects.all()

    selected_category = category or request.GET.get("category")
    search_query = request.GET.get("q")

    # Validate and parse min_price and max_price
    try:
        min_price = Decimal(request.GET.get("min_price", "0"))
    except (ValueError, InvalidOperation):
        min_price = Decimal("0")

    try:
        max_price = Decimal(request.GET.get("max_price", "1000"))
    except (ValueError, InvalidOperation):
        max_price = Decimal("1000")

    sort_option = request.GET.get("sort", "featured")

    if selected_category and selected_category.lower() != "all":
        products = products.filter(category__name=selected_category)

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    for product in products:
        product.price_display = product.price_in_peso

    address = None
    wishlist_product_ids = []
    products_in_cart = []
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass
        wishlist_product_ids = models.ProductWishlist.objects.filter(
            user=request.user
        ).values_list("product_id", flat=True)

    context = {
        "products": products,
        "categories": categories,
        "selected_category": selected_category,
        "user_address": address,
        "wishlist_product_ids": wishlist_product_ids
    }

    return render(request, "store/products.html", context)


def product_details(request, product_id):
    product = get_object_or_404(models.Product, id=product_id)
    product.price_display = product.price_in_peso
    address = None
    cart_item_exist = False
    wishlist_product_ids = []
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass
        
        cart_item_exist = models.CartItem.objects.filter(
            user=request.user, product=product
        ).exists()
        wishlist_product_ids = list(
            models.ProductWishlist.objects.filter(user=request.user)
                    .values_list('product_id', flat=True)
        )

    context = {
        "product": product,
        "user_address": address,
        "wishlist_product_ids": wishlist_product_ids,
        "cart_item_exist": cart_item_exist
    }
    return render(request, "store/product-detail.html", context)


@login_required(login_url="/login")
def cart_view(request):
    cart_items = models.CartItem.objects.filter(user=request.user)

    sub_total = sum(
        item.product.discounted_price * item.quantity for item in cart_items
    )

    promo_discount = request.session.get("promo_discount", 0)
    voucher_discount = (sub_total * promo_discount) // 100 if promo_discount else 0
    to_pay = sub_total - voucher_discount

    # Fetch user's shipping address
    try:
        user_address = models.ShippingAddress.objects.get(user=request.user)
    except models.ShippingAddress.DoesNotExist:
        user_address = None

    # Calculate total price for each cart item
    for item in cart_items:
        item.total_price = item.product.discounted_price * item.quantity

    context = {
        "cart_items": cart_items if cart_items else [],
        "sub_total": sub_total,
        "to_pay": to_pay,
        "voucher_discount": voucher_discount,
        "user_address": user_address,
    }

    return render(request, "store/cart.html", context)


@login_required(login_url="/login")
def add_to_cart(request, product_id):
    if request.method == "POST":
        quantity = request.POST.get("quantity", 1)
        product = models.Product.objects.get(id=product_id)
        cart_item, created = models.CartItem.objects.get_or_create(
            user=request.user, product=product, defaults={"quantity": quantity}
        )

        if not created:
            cart_item.quantity += 1
            cart_item.save()

        # AJAX request: return JSON to prevent full page reload
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            total_quantity = (
                models.CartItem.objects.filter(user=request.user).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )
            return JsonResponse(
                {
                    "success": True,
                    "quantity": cart_item.quantity,
                    "cart_total": total_quantity,
                }
            )

    return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))


@login_required(login_url="/login")
def remove_from_cart(request, product_id):
    if request.method == "POST":
        try:
            product = models.Product.objects.get(id=product_id)
            cart_item = models.CartItem.objects.get(user=request.user, product=product)
            cart_item.delete()
            return JsonResponse({"success": True})
        except models.CartItem.DoesNotExist:
            return JsonResponse({"success": False})
    return JsonResponse({"success": False})


@login_required(login_url="/login")
def update_cart(request, product_id):
    if request.method == "POST":
        quantity = request.POST.get("quantity")
        try:
            product = models.Product.objects.get(id=product_id)
            cart_item = models.CartItem.objects.get(user=request.user, product=product)
            cart_item.quantity = quantity
            cart_item.save()
        except models.CartItem.DoesNotExist:
            pass

    if "HTTP_REFERER" in request.META:
        request.session["last_page"] = request.META["HTTP_REFERER"]

    return redirect(request.session.get("last_page", "/default-redirect-url"))


@require_POST
@login_required(login_url="/login")
def toggle_wishlist(request):
    if request.method == "POST":
        product_id = request.POST.get("product_id")
        try:
            product = models.Product.objects.get(id=product_id)
            wishlist_item, created = models.ProductWishlist.objects.get_or_create(
                user=request.user, product=product
            )
            if not created:
                wishlist_item.delete()
                in_wishlist = False
            else:
                in_wishlist = True
            return JsonResponse({"success": True, "in_wishlist": in_wishlist})
        except models.Product.DoesNotExist:
            return JsonResponse({"success": False}, status=404)


@login_required(login_url="/login")
def add_to_wishlist(request, product_id):
    if request.method == "POST":
        product = models.Product.objects.get(id=product_id)
        models.ProductWishlist.objects.get_or_create(user=request.user, product=product)

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            in_wishlist = models.ProductWishlist.objects.filter(
                user=request.user, product=product
            ).exists()
            return JsonResponse({"success": True, "in_wishlist": in_wishlist})

    return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))


@login_required(login_url="/login")
def remove_from_wishlist(request, product_id):
    if request.method == "POST":
        models.ProductWishlist.objects.filter(
            user=request.user, product_id=product_id
        ).delete()

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            in_wishlist = models.ProductWishlist.objects.filter(
                user=request.user, product_id=product_id
            ).exists()
            return JsonResponse({"success": True, "in_wishlist": in_wishlist})

    return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))


@login_required(login_url="/login")
def wishlist_view(request):
    wishlist_qs = models.ProductWishlist.objects.filter(
        user=request.user
    ).select_related("product")
    products = [item.product for item in wishlist_qs]

    return render(request, "store/wishlist-page.html", {"wishlist": products})


@login_required(login_url="/login")
def checkout_view(request):
    cart_items = models.CartItem.objects.filter(user=request.user)
    user_address, created = models.ShippingAddress.objects.get_or_create(
        user=request.user
    )
    promo_discount = request.session.get("promo_discount", 0)

    sub_total = sum(
        item.product.discounted_price * item.quantity for item in cart_items
    )

    shipping = 120
    promo_discount = request.session.get("promo_discount", 0)
    voucher_discount = (sub_total * promo_discount) // 100 if promo_discount else 0

    to_pay = sub_total - voucher_discount + shipping

    if request.method == "POST":
        if not user_address.full_name or not user_address.address:
            messages.error(
                request,
                "Please add a shipping address before placing your order.",
                extra_tags="checkout-msg",
            )
            return redirect("checkout-view")

        notes = request.POST.get("notes")

        promo_code_str = request.session.get("promo_code")
        promo_code = None

        if promo_code_str:
            try:
                promo_code = models.PromoCode.objects.get(
                    code=promo_code_str, active=True
                )
            except models.PromoCode.DoesNotExist:
                promo_code = None

        order = models.Order.objects.create(
            user=request.user,
            user_note=notes,
            shipping_price=shipping,
            discount=voucher_discount,
            total_price=to_pay,
        )

        if promo_code:
            models.PromoCodeUsage.objects.create(
                user=request.user, promo_code=promo_code, order=order
            )

        choosen_payment_method = request.POST.get("selected_payment")
        payment_method = models.PaymentMethod.objects.create(
            user=request.user,
            order=order,
            payment_method=choosen_payment_method,
            amount=to_pay,
        )

        for item in cart_items:
            models.OrderItem.objects.create(
                order=order,
                product=item.product,
                quantity=item.quantity,
                price=item.product.price,
                total_price=item.quantity * item.product.discounted_price,
            )

        order.save()

        cart_items.delete()

        request.session["last_order_data"] = {
            "order_id": order.id,
            "voucher_discount": float(voucher_discount),
            "promo_code": request.session.get("promo_code"),
            "shipping": float(shipping),
            "to_pay": float(to_pay),
            "payment_method": payment_method.payment_method,
        }

        request.session.pop("promo_discount", None)
        request.session.pop("promo_code", None)

        return redirect("order-success-page")

    context = {
        "cart_items": cart_items,
        "user_address": user_address,
        "sub_total": sub_total,
        "shipping": shipping,
        "to_pay": to_pay,
        "voucher_discount": voucher_discount,
    }
    return render(request, "store/checkout-page.html", context)


@login_required(login_url="/login")
def order_success_page(request):
    order_data = request.session.get("last_order_data", {})

    if not order_data:
        return redirect("store")

    order = get_object_or_404(models.Order, id=order_data.get("order_id"))

    order = get_object_or_404(models.Order, id=order_data.get("order_id"))

    payment = models.PaymentMethod.objects.filter(order=order).first()

    payment_method = order_data.get("payment_method")

    order.generate_next_update_time()

    address = None
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass

    context = {
        "order": order,
        "order_items": order.order_items.all(),
        "voucher_discount": order_data.get("voucher_discount", 0),
        "promo_code": order_data.get("promo_code"),
        "shipping": order_data.get("shipping", 0),
        "total_price": order.total_price,
        "payment": payment,
        "user_address": address,
        "payment_method": payment_method,
    }
    
    # Admin email (order summary)
    admin_email_subject = "New Order Received"
    admin_email_body = render_to_string(
        "store/emails/admin_order_summary.html", context
    )
    admin_email_message = EmailMessage(
        admin_email_subject,
        admin_email_body,
        f"ShopNow <{settings.EMAIL_HOST_USER}>",
        [settings.EMAIL_HOST_USER],
    )
    admin_email_message.content_subtype = "html"
    admin_email_message.send(fail_silently=False)


    # User email (receipt)
    user_email_subject = "Your Order Receipt"
    user_email_body = render_to_string(
        "store/emails/user_order_receipt.html", context
    )
    user_email_message = EmailMessage(
        user_email_subject,
        user_email_body,
        f"ShopNow <{settings.EMAIL_HOST_USER}>",
        [request.user.email],
    )
    user_email_message.content_subtype = "html"
    user_email_message.send(fail_silently=False)

    messages.success(
        request,
        "Thank you for your order! A receipt has been sent to your email.",
        extra_tags="order-success-msg",
    )

    return render(request, "store/order-success-page.html", context)


@login_required(login_url="/login")
def order_details_view(request, order_id):
    order = get_object_or_404(models.Order, id=order_id, user=request.user)

    user_address = models.ShippingAddress.objects.get(user=request.user)
    payment_method = models.PaymentMethod.objects.get(order=order)

    promo_code_usage = models.PromoCodeUsage.objects.filter(order=order).first()
    promo_code = promo_code_usage.promo_code if promo_code_usage else None
    address = None
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass
    context = {
        "order": order,
        "order_items": order.order_items.all(),
        "user_address": user_address,
        "payment": payment_method,
        "promo_code": promo_code,
        "user_address": address,
    }

    return render(request, "store/order-details.html", context)


@login_required(login_url="/login")
def apply_promo(request):
    if request.method == "POST":
        code = request.POST.get("promo_code", "").strip()

        if not code:
            request.session.pop("promo_code", None)
            request.session.pop("promo_discount", None)
            messages.info(request, "Promo code cleared.", extra_tags="cart-msg")
            return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))

        try:
            promo = models.PromoCode.objects.get(code__iexact=code)

            # Check if promo code is valid
            if promo.is_valid_for_user(request.user):
                # Store promo code and discount percentage in session for cart view
                request.session["promo_code"] = promo.code
                request.session["promo_discount"] = promo.discount_percentage
                messages.success(
                    request,
                    f"Promo code '{promo.code}' applied successfully! You get a {promo.discount_percentage}% discount.",
                    extra_tags="cart-msg",
                )
            else:
                messages.error(
                    request,
                    "Promo code is expired, inactive, or you've exceeded the usage limit.",
                    extra_tags="cart-msg",
                )
        except models.PromoCode.DoesNotExist:
            messages.error(request, "Invalid promo code.", extra_tags="cart-msg")

    return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))


@login_required(login_url="/login")
def contact(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        subject = request.POST.get("subject")
        message = request.POST.get("message")

        email_subject = f"Contact Form Submission: {subject}"
        email_body = (
            "Dear Support Team,\n\n"
            "You have received a new inquiry via the website contact form. Please find the details below:\n\n"
            f"Name       : {name}\n"
            f"Email       : {email}\n"
            f"Subject    : {subject}\n\n"
            "Message:\n"
            f"{message.strip()}\n\n"
            "Please follow up with the sender as appropriate.\n\n"
            "Regards,\n"
            "Website Contact Form Notification System"
        )

        send_mail(
            email_subject,
            email_body,
            f"ShopNow <{settings.EMAIL_HOST_USER}>",
            [settings.EMAIL_HOST_USER],
            fail_silently=False,
        )

        messages.success(
            request,
            "Thank you for reaching out! Our team will respond to your message shortly.",
            extra_tags="contact-msg",
        )
        return redirect("contact")

    return render(request, "store/contact.html")


def search_product(request):
    products = []
    query = ""

    if request.method == "POST":
        query = request.POST.get("query", "")

        if query:
            name_matches = models.Product.objects.filter(name__icontains=query)
            if name_matches.exists():
                products = name_matches
            else:
                category = models.Category.objects.filter(name__iexact=query).first()
                if category:
                    products = models.Product.objects.filter(category=category)

    context = {"products": products, "query": query}
    return render(request, "store/search-results.html", context)


@login_required(login_url="/login")
def product_review_view(request, order_id):
    order = get_object_or_404(models.Order, id=order_id)
    reviewed_products_id = models.ProductReview.objects.filter(
        user=request.user,
        product__in=[item.product for item in order.order_items.all()],
    ).values_list("product_id", flat=True)

    return render(
        request,
        "store/product-review-page.html",
        {"order": order, "reviewed_product_ids": reviewed_products_id},
    )


@login_required(login_url="/login")
def add_review(request, product_id):
    if request.method == "POST":
        rating = request.POST.get("rating")
        review = request.POST.get("review")

        product = models.Product.objects.get(id=product_id)

        product_review = models.ProductReview.objects.create(
            product=product, user=request.user, rating=rating, review=review
        )
        product_review.save()

    return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))


@login_required(login_url="/login")
def orders_view(request):
    orders = models.Order.objects.filter(user=request.user)

    for order in orders:
        if order.next_status_update and timezone.now() >= order.next_status_update:
            order.advance_status()
    
    address = None
    if request.user.is_authenticated:
        try:
            address = models.ShippingAddress.objects.get(user=request.user)
        except models.ShippingAddress.DoesNotExist:
            pass

    return render(
        request,
        "store/orders.html",
        {
            "orders": orders,
            "user_address": address,
        },
    )


@require_POST
@login_required(login_url="/login")
def subscribe_email(request):
    user_email = request.user.email

    if request.method == "POST":
        sub = models.Subscriber.objects.filter(email=user_email).first()
        if sub:
            sub.delete()
        else:
            models.Subscriber.objects.create(email=user_email)
        return redirect(request.META.get("HTTP_REFERER", "default-redirect-url"))
