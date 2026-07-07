import json
import os
import re
import difflib
import traceback
from datetime import datetime, timedelta

# Google Sheets اختياري: إذا لم يكن مضبوطًا يرجع البوت إلى products.json
try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import TOKEN, ADMIN_CHAT_ID
ORDERS_FILE = "orders.json"

# ===== Google Sheets Settings =====
# ضع هذه القيم في Railway Variables:
# GOOGLE_SHEET_ID = رقم/معرف ملف Google Sheet
# GOOGLE_PRODUCTS_WORKSHEET = Products
# GOOGLE_ORDERS_WORKSHEET = Orders
# GOOGLE_SERVICE_ACCOUNT_JSON = محتوى ملف service account بصيغة JSON
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_PRODUCTS_WORKSHEET = os.getenv("GOOGLE_PRODUCTS_WORKSHEET", "Products").strip()
GOOGLE_ORDERS_WORKSHEET = os.getenv("GOOGLE_ORDERS_WORKSHEET", "Orders").strip()
PRODUCTS_CACHE_TTL_SECONDS = int(os.getenv("PRODUCTS_CACHE_TTL_SECONDS", "60"))

_products_cache = {
    "loaded_at": None,
    "data": [],
}


main_keyboard = [
    ["💊 المنتجات", "🔍 البحث عن منتج"],
    ["✨ العناية بالبشرة", "💇 العناية بالشعر"],
    ["👶 الأم والطفل", "🩺 اسأل الصيدلي"],
    ["🎁 العروض", "🛒 السلة"],
    ["📦 طلباتي", "📞 تواصل معنا"],
]

products_keyboard = [
    ["💊 أدوية OTC", "💪 مكملات غذائية"],
    ["✨ مستحضرات تجميل", "👶 مستلزمات أطفال"],
    ["🩺 أجهزة طبية"],
    ["🔙 رجوع للقائمة الرئيسية"],
]



def normalize_header(header):
    return normalize_text(header).replace(" ", "_")


def first_value(row, *keys, default=""):
    for key in keys:
        value = row.get(key)
        if value not in [None, ""]:
            return value
    return default


def split_keywords(value):
    if isinstance(value, list):
        return value
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in re.split(r"[,،;؛\\n]+", text) if item.strip()]


def truthy(value):
    text = str(value or "").strip().lower()
    return text in ["1", "true", "yes", "y", "متوفر", "نعم", "available"]


def get_google_client():
    if not GOOGLE_SHEET_ID or gspread is None or Credentials is None:
        return None

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    try:
        if service_account_json:
            info = json.loads(service_account_json)
            credentials = Credentials.from_service_account_info(info, scopes=scopes)
        elif os.path.exists("service_account.json"):
            credentials = Credentials.from_service_account_file("service_account.json", scopes=scopes)
        else:
            print("GOOGLE_SHEETS_NOT_CONFIGURED: missing GOOGLE_SERVICE_ACCOUNT_JSON or service_account.json")
            return None

        return gspread.authorize(credentials)

    except Exception as e:
        print(f"GOOGLE_CLIENT_ERROR: {e}")
        return None


def sheet_row_to_product(row):
    # يدعم أسماء أعمدة عربية وإنجليزية
    product = {
        "id": first_value(row, "id", "كود", "رقم", default=""),
        "name": first_value(row, "name", "اسم_المنتج", "الاسم", "اسم", default="").strip(),
        "category": first_value(row, "category", "التصنيف", "القسم", default="OTC"),
        "cost_price": first_value(row, "cost_price", "سعر_الشراء", "سعر_التكلفه", "تكلفه", default=""),
        "price": first_value(row, "sell_price", "price", "سعر_البيع", "السعر", default="0"),
        "sell_price_box": first_value(row, "sell_price_box", "سعر_العلبه", "سعر_البيع", "sell_price", "price", default="0"),
        "sell_price_strip": first_value(row, "sell_price_strip", "سعر_الشريط", default="0"),
        "description": first_value(row, "description", "الوصف", "الاستخدام", default=""),
        "therapeutic_class": first_value(row, "therapeutic_class", "الفئه_العلاجيه", "التصنيف_العلاجي", "نوع_العلاج", default=""),
        "active_ingredient_or_equivalent": first_value(row, "active_ingredient", "الماده_الفعاله", "المادة_الفعالة", "equivalent", default=""),
        "image": first_value(row, "image", "رابط_الصوره", "الصوره", default=""),
        "brand": first_value(row, "brand", "الشركه", default=""),
        "pack_size": first_value(row, "pack_size", "حجم_العبوه", default=""),
        "pack_unit": first_value(row, "pack_unit", "وحده_العبوه", default=""),
        "strips_count": first_value(row, "strips_count", "عدد_الاشرطه", default=""),
        "units_per_strip": first_value(row, "units_per_strip", "عدد_الوحدات_في_الشريط", default=""),
        "available": first_value(row, "available", "الحاله", "متوفر", default="متوفر"),
        "can_sell_strip": truthy(first_value(row, "can_sell_strip", "بيع_بالشريط", default="")),
        "keywords": split_keywords(first_value(row, "keywords", "كلمات_مفتاحيه", "كلمات_البحث", default="")),
        "aliases": split_keywords(first_value(row, "aliases", "اسماء_شائعه", "اسماء_اخرى", default="")),
    }

    return product


def load_products_from_google_sheets():
    client = get_google_client()
    if client is None:
        return None

    try:
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sheet.worksheet(GOOGLE_PRODUCTS_WORKSHEET)
        rows = worksheet.get_all_records()

        products = []
        for raw_row in rows:
            normalized_row = {
                normalize_header(k): v
                for k, v in raw_row.items()
            }
            product = sheet_row_to_product(normalized_row)

            if not product.get("name"):
                continue

            if str(product.get("available", "")).strip() in ["غير متوفر", "0", "false", "False", "no", "No"]:
                continue

            products.append(product)

        print(f"GOOGLE_PRODUCTS_LOADED: {len(products)} products")
        return products

    except Exception as e:
        print(f"GOOGLE_SHEETS_PRODUCTS_ERROR: {e}")
        return None


def append_order_to_google_sheets(order):
    client = get_google_client()
    if client is None:
        return

    try:
        sheet = client.open_by_key(GOOGLE_SHEET_ID)

        try:
            worksheet = sheet.worksheet(GOOGLE_ORDERS_WORKSHEET)
        except Exception:
            worksheet = sheet.add_worksheet(title=GOOGLE_ORDERS_WORKSHEET, rows=1000, cols=12)
            worksheet.append_row([
                "order_id", "status", "customer_name", "customer_phone", "customer_address",
                "items", "total", "customer_chat_id", "created_at", "updated_at"
            ])

        items_text = " | ".join(
            f"{item.get('name')} ({item.get('unit_label', 'علبة')}) x {item.get('qty')} = {item.get('subtotal')}"
            for item in order.get("items", [])
        )

        worksheet.append_row([
            order.get("id"),
            order.get("status"),
            order.get("customer_name"),
            order.get("customer_phone"),
            order.get("customer_address"),
            items_text,
            order.get("total"),
            order.get("customer_chat_id"),
            order.get("created_at"),
            order.get("updated_at", ""),
        ])

    except Exception as e:
        print(f"GOOGLE_SHEETS_ORDER_APPEND_ERROR: {e}")


def load_products():
    now = datetime.now()

    # 1) جرّب Google Sheets مع كاش لمدة دقيقة حتى لا يكون البوت بطيئًا
    if GOOGLE_SHEET_ID:
        loaded_at = _products_cache.get("loaded_at")
        cached_data = _products_cache.get("data", [])

        if loaded_at and cached_data and (now - loaded_at).total_seconds() < PRODUCTS_CACHE_TTL_SECONDS:
            return cached_data

        sheet_products = load_products_from_google_sheets()
        if sheet_products is not None:
            _products_cache["loaded_at"] = now
            _products_cache["data"] = sheet_products
            return sheet_products

    # 2) fallback: إذا Google Sheets لم يعمل، استخدم products.json
    try:
        with open("products.json", "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        if isinstance(data, dict) and isinstance(data.get("products"), list):
            return data["products"]

        print("PRODUCTS_FILE_FORMAT_ERROR")
        return []

    except Exception as e:
        print(f"LOAD_PRODUCTS_ERROR: {e}")
        return []


def load_orders():
    if not os.path.exists(ORDERS_FILE):
        return []
    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_orders(orders):
    with open(ORDERS_FILE, "w", encoding="utf-8") as file:
        json.dump(orders, file, ensure_ascii=False, indent=2)


def create_order_id():
    return len(load_orders()) + 1001


def product_by_name(product_name: str):
    return next((p for p in load_products() if p.get("name") == product_name), None)


def product_by_index(index: int):
    products = load_products()
    if 0 <= index < len(products):
        return products[index]
    return None


def product_index_by_name(product_name: str):
    for idx, product in enumerate(load_products()):
        if product.get("name") == product_name:
            return idx
    return -1


def normalize_text(text: str):
    text = str(text).strip().lower()
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def product_search_text(product):
    parts = [
        product.get("name", ""),
        product.get("description", ""),
        product.get("category", ""),
        product.get("therapeutic_class", ""),
        product.get("active_ingredient_or_equivalent", ""),
        product.get("brand", ""),
    ]

    for field in ["keywords", "aliases"]:
        values = product.get(field, [])
        if isinstance(values, list):
            parts.extend(values)
        elif isinstance(values, str):
            parts.append(values)

    return " ".join(str(p) for p in parts if p)


def search_products(query: str, limit: int = 8):
    query_norm = normalize_text(query)
    if not query_norm:
        return []
    scored = []
    for idx, product in enumerate(load_products()):
        try:
            if not isinstance(product, dict):
                continue
            combined = normalize_text(product_search_text(product))
            name_norm = normalize_text(product.get("name", ""))
            if not name_norm:
                continue
            score = 0.0
            if query_norm in name_norm:
                score = 1.0
            elif query_norm in combined:
                score = 0.9
            words = combined.split()
            if words:
                score = max(score, max((difflib.SequenceMatcher(None, query_norm, w).ratio() for w in words), default=0))
            score = max(score, difflib.SequenceMatcher(None, query_norm, name_norm).ratio())
            if score >= 0.40:
                scored.append((score, idx, product))
        except Exception as e:
            print(f"SEARCH_PRODUCT_ERROR {idx}: {e}")
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def search_results_keyboard(results):
    buttons = []
    for score, idx, product in results:
        name = product.get("name", "منتج")
        buttons.append([InlineKeyboardButton(f"💊 {name}", callback_data=f"product:view:{idx}")])
    buttons.append([InlineKeyboardButton("🔍 بحث جديد", callback_data="search:new")])
    buttons.append([InlineKeyboardButton("🛒 عرض السلة", callback_data="cart:view")])
    return InlineKeyboardMarkup(buttons)


def to_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text or text.lower() in ["#n/a", "nan", "none", "null"]:
            return default
        match = re.search(r"\d+(?:\.\d+)?", text)
        return float(match.group()) if match else default
    except Exception:
        return default


def product_box_price(product):
    return to_float(product.get("sell_price_box") or product.get("price") or product.get("sell_price") or 0)


def product_strip_price(product):
    return to_float(product.get("sell_price_strip") or 0)


def product_pack_info(product):
    pack_size = product.get("pack_size")
    pack_unit = product.get("pack_unit", "")
    strips_count = product.get("strips_count")
    units_per_strip = product.get("units_per_strip")

    parts = []
    if pack_size:
        parts.append(f"{pack_size} {pack_unit}".strip())
    if strips_count:
        parts.append(f"{strips_count} شريط")
    if units_per_strip:
        parts.append(f"{units_per_strip} وحدة/شريط")
    return " - ".join(parts) if parts else "غير محدد"


def product_type(product):
    return (
        product.get("therapeutic_class")
        or product.get("type")
        or product.get("description")
        or "غير مصنف"
    )


def active_ingredient(product):
    return (
        product.get("active_ingredient_or_equivalent")
        or product.get("active_ingredient")
        or ""
    )


def can_sell_strip(product):
    value = product.get("can_sell_strip", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["true", "1", "yes", "y"]


def unit_label(unit):
    return "علبة" if unit == "box" else "شريط"


def unit_price(product, unit):
    if unit == "strip":
        return product_strip_price(product)
    return product_box_price(product)


def cart_key(product_name, unit):
    return f"{product_name}__{unit}"


def parse_price(price_value):
    """Extract a numeric price from values like '12 شيكل' or 12."""
    if isinstance(price_value, (int, float)):
        return float(price_value)
    text = str(price_value)
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else 0.0


def format_price(value: float):
    if float(value).is_integer():
        return f"{int(value)} شيكل"
    return f"{value:.2f} شيكل"


def get_cart(context: ContextTypes.DEFAULT_TYPE):
    if "cart" not in context.user_data:
        context.user_data["cart"] = {}
    return context.user_data["cart"]


def cart_total(cart):
    total = 0.0
    for item in cart.values():
        total += float(item.get("price", 0)) * int(item.get("qty", 1))
    return total


def cart_count(cart):
    return sum(int(item.get("qty", 1)) for item in cart.values())


def cart_text(cart):
    if not cart:
        return "🛒 سلة المشتريات فارغة حالياً."

    lines = ["🛒 سلة مشترياتك\n"]
    for i, item in enumerate(cart.values(), start=1):
        qty = int(item.get("qty", 1))
        price = float(item.get("price", 0))
        subtotal = qty * price
        unit = item.get("unit_label", "علبة")
        lines.append(f"{i}. {item['name']} ({unit}) × {qty} = {format_price(subtotal)}")

    lines.append("\n━━━━━━━━━━━━")
    lines.append(f"💰 الإجمالي: {format_price(cart_total(cart))}")
    return "\n".join(lines)


def cart_keyboard(cart):
    buttons = []

    for item in cart.values():
        product_name = item.get("name")
        unit = item.get("unit", "box")
        idx = product_index_by_name(product_name)
        if idx == -1:
            continue

        label = f"{product_name} ({unit_label(unit)})"
        buttons.append([
            InlineKeyboardButton(f"➖ {label}", callback_data=f"cart:dec:{idx}:{unit}"),
            InlineKeyboardButton("➕", callback_data=f"cart:inc:{idx}:{unit}"),
            InlineKeyboardButton("🗑️", callback_data=f"cart:remove:{idx}:{unit}"),
        ])

    buttons.append([InlineKeyboardButton("➕ متابعة التسوق", callback_data="cart:continue")])
    if cart:
        buttons.append([InlineKeyboardButton("✅ إتمام الطلب", callback_data="cart:checkout")])
        buttons.append([InlineKeyboardButton("🗑️ إفراغ السلة", callback_data="cart:clear")])

    return InlineKeyboardMarkup(buttons)


def checkout_interrupt_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 متابعة التسوق", callback_data="checkout_interrupt:shop")],
        [InlineKeyboardButton("✅ متابعة إتمام الطلب", callback_data="checkout_interrupt:checkout")],
    ])


def clean_button_text(text: str):
    text = str(text).strip()
    for ch in ["💊", "🔍", "✨", "💇", "👶", "🩺", "🎁", "🛒", "📦", "📞", "💪", "🔙", "🏠"]:
        text = text.replace(ch, "")
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def canonical_text(text: str):
    original = str(text).strip()
    cleaned = clean_button_text(original)
    if "otc" in cleaned or "ادويه" in cleaned or "ادوية" in cleaned:
        return "💊 أدوية OTC"
    if "بحث" in cleaned:
        return "🔍 البحث عن منتج"
    if "منتجات" in cleaned:
        return "💊 المنتجات"
    if "السله" in cleaned or "السلة" in cleaned:
        return "🛒 السلة"
    if "رجوع" in cleaned and "رئيس" in cleaned:
        return "🔙 رجوع للقائمة الرئيسية"
    if "رجوع" in cleaned:
        return "🔙 رجوع للمنتجات"
    return original




def is_same_button(text: str, label: str):
    return canonical_text(text) == label


def is_navigation_or_product_text(text: str):
    text = canonical_text(text)
    navigation_buttons = {
        "💊 المنتجات",
        "🔍 البحث عن منتج",
        "💊 أدوية OTC",
        "💪 مكملات غذائية",
        "✨ مستحضرات تجميل",
        "👶 مستلزمات أطفال",
        "🩺 أجهزة طبية",
        "🔙 رجوع للمنتجات",
        "🔙 رجوع للقائمة الرئيسية",
        "✨ العناية بالبشرة",
        "💇 العناية بالشعر",
        "👶 الأم والطفل",
        "🩺 اسأل الصيدلي",
        "🎁 العروض",
        "🛒 السلة",
        "📦 طلباتي",
        "📞 تواصل معنا",
    }
    product_names = [p["name"] for p in load_products()]
    return text in navigation_buttons or text in product_names


def is_otc_product(product):
    category = normalize_text(product.get("category", ""))
    therapeutic = normalize_text(product.get("therapeutic_class", ""))
    name = normalize_text(product.get("name", ""))
    return (
        category in ["otc", "ادويه otc", "ادوية otc"]
        or "otc" in category
        or "مسكن" in therapeutic
        or "خافض" in therapeutic
        or "معده" in therapeutic
        or "حساسيه" in therapeutic
    )


def product_list_keyboard(products, max_items=30):
    keyboard = []
    for product in products[:max_items]:
        name = product.get("name")
        if name:
            keyboard.append([name])
    keyboard.append(["🔍 البحث عن منتج"])
    keyboard.append(["🔙 رجوع للمنتجات"])
    return keyboard


async def show_products_menu_to_message(message):
    await message.reply_text(
        "💊 قسم المنتجات\n\nاختر القسم الذي تريده:",
        reply_markup=ReplyKeyboardMarkup(products_keyboard, resize_keyboard=True),
    )


async def show_otc_products_to_message(message):
    await message.reply_text(
        "💊 قسم أدوية OTC\n\nاكتب اسم المنتج أو جزءًا منه الآن للبحث داخل الأدوية.\n\nمثال: Panadol / Brufen / Abimol / فيتامين",
        reply_markup=ReplyKeyboardMarkup([["🔍 البحث عن منتج"], ["🔙 رجوع للمنتجات"]], resize_keyboard=True),
    )


async def show_product_details_to_message(message, product_name: str):
    product = product_by_name(product_name)

    if product is None:
        await message.reply_text("لم يتم العثور على المنتج.")
        return

    idx = product_index_by_name(product_name)

    box_price = product_box_price(product)
    strip_price = product_strip_price(product)
    pack_info = product_pack_info(product)
    therapeutic = product_type(product)
    active = active_ingredient(product)

    caption = (
        f"💊 {product['name']}\n\n"
        f"💰 سعر العلبة: {format_price(box_price)}\n"
    )

    if can_sell_strip(product) and strip_price > 0:
        caption += f"💊 سعر الشريط: {format_price(strip_price)}\n"

    caption += (
        f"📦 العبوة: {pack_info}\n"
        f"🩺 التصنيف: {therapeutic}\n"
    )

    if active:
        caption += f"🧪 المادة الفعالة/المكافئ: {active}\n"

    if product.get("needs_review"):
        caption += "\n⚠️ تفاصيل الشرائط تقديرية وتحتاج مراجعة من الصيدلية."

    product_button_rows = [
        [InlineKeyboardButton("🛒 إضافة علبة للسلة", callback_data=f"cart:add:{idx}:box")]
    ]

    if can_sell_strip(product) and strip_price > 0:
        product_button_rows.append([
            InlineKeyboardButton("💊 إضافة شريط للسلة", callback_data=f"cart:add:{idx}:strip")
        ])

    product_button_rows.append([InlineKeyboardButton("🛒 عرض السلة", callback_data="cart:view")])
    product_button_rows.append([InlineKeyboardButton("⚡ اطلب علبة الآن", callback_data=f"order:{product['name']}")])

    product_buttons = InlineKeyboardMarkup(product_button_rows)

    image_path = product.get("image", "")

    if image_path:
        try:
            with open(image_path, "rb") as photo:
                await message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=product_buttons,
                )
        except FileNotFoundError:
            await message.reply_text(
                caption + "\n\n⚠️ الصورة غير موجودة.",
                reply_markup=product_buttons,
            )
    else:
        await message.reply_text(caption, reply_markup=product_buttons)


async def route_shop_text_to_message(message, context: ContextTypes.DEFAULT_TYPE, text: str):
    text = canonical_text(text)
    product_names = [p["name"] for p in load_products()]

    if text == "💊 المنتجات":
        await show_products_menu_to_message(message)

    elif text == "💊 أدوية OTC":
        await show_otc_products_to_message(message)

    elif text in product_names:
        await show_product_details_to_message(message, text)

    elif text == "🔍 البحث عن منتج":
        context.user_data["search_step"] = True
        await message.reply_text(
            "🔍 اكتب اسم المنتج أو جزءًا منه:\n\n"
            "مثال: Panadol / Brufen / فيتامين / صداع"
        )

    elif text == "🛒 السلة":
        cart = get_cart(context)
        await message.reply_text(cart_text(cart), reply_markup=cart_keyboard(cart))

    elif text == "🔙 رجوع للمنتجات":
        await show_products_menu_to_message(message)

    elif text == "🔙 رجوع للقائمة الرئيسية":
        await message.reply_text(
            "🏠 القائمة الرئيسية\n\nاختر الخدمة التي تريدها:",
            reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True),
        )

    elif text == "💪 مكملات غذائية":
        await message.reply_text("💪 مكملات غذائية\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "✨ مستحضرات تجميل":
        await message.reply_text("✨ مستحضرات تجميل\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "👶 مستلزمات أطفال":
        await message.reply_text("👶 مستلزمات أطفال\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "🩺 أجهزة طبية":
        await message.reply_text("🩺 أجهزة طبية\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "✨ العناية بالبشرة":
        await message.reply_text("✨ قريبًا: اكتشف روتين بشرتك حسب نوع البشرة والمشكلة.")

    elif text == "💇 العناية بالشعر":
        await message.reply_text("💇 قريبًا: تحليل مشكلة الشعر واقتراح المنتجات المناسبة.")

    elif text == "👶 الأم والطفل":
        await message.reply_text("👶 قسم الأم والطفل قيد التجهيز.")

    elif text == "🩺 اسأل الصيدلي":
        await message.reply_text("🩺 اكتب سؤالك هنا، وسيتم تحويله للصيدلي للرد عليك.")

    elif text == "🎁 العروض":
        await message.reply_text("🎁 لا توجد عروض مضافة حاليًا.")

    elif text == "📦 طلباتي":
        await message.reply_text("📦 قريبًا يمكنك متابعة طلباتك من هنا.")

    elif text == "📞 تواصل معنا":
        await message.reply_text(
            "📞 للتواصل معنا:\n"
            "واتساب: ضع رقمك هنا\n"
            "تيليجرام: @ضع_اسمك_هنا"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = """
💚 أهلاً بك في صيدليتك

🩺 صيدليتك الذكية... صحتك بين يديك.

اختر الخدمة التي تريدها من القائمة بالأسفل 👇
"""

    reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

    try:
        with open("images/welcome.png", "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
            )
    except FileNotFoundError:
        await update.message.reply_text(
            caption + "\n⚠️ لم يتم العثور على صورة الترحيب images/welcome.png",
            reply_markup=reply_markup,
        )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ هذه اللوحة خاصة بالإدارة فقط.")
        return

    orders = load_orders()
    new_orders = [o for o in orders if o.get("status") == "new"]

    await update.message.reply_text(
        "🛠 لوحة الإدارة\n\n"
        f"📦 إجمالي الطلبات: {len(orders)}\n"
        f"🆕 الطلبات الجديدة: {len(new_orders)}"
    )


async def show_products_menu(update: Update):
    await show_products_menu_to_message(update.message)


async def show_otc_products(update: Update):
    await show_otc_products_to_message(update.message)


async def show_product_details(update: Update, product_name: str):
    await show_product_details_to_message(update.message, product_name)


async def show_search_results_message(message, context: ContextTypes.DEFAULT_TYPE, query: str):
    results = search_products(query)

    if not results:
        await message.reply_text(
            "❌ لم أجد منتجًا مطابقًا.\n\n"
            "جرّب كتابة جزء من الاسم أو اسمًا آخر.\n"
            "مثال: panadol / brufen / فيتامين"
        )
        return

    lines = [f"🔎 نتائج البحث عن: {query}\n"]
    for i, (score, idx, product) in enumerate(results, start=1):
        lines.append(f"{i}. 💊 {product.get('name')}")

    await message.reply_text(
        "\n".join(lines),
        reply_markup=search_results_keyboard(results),
    )


async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["search_step"] = True
    await query.message.reply_text(
        "🔍 اكتب اسم المنتج أو جزءًا منه:\n\n"
        "مثال: Panadol / Brufen / فيتامين / صداع"
    )


async def show_product_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split(":")[-1])
    product = product_by_index(idx)

    if product is None:
        await query.message.reply_text("❌ المنتج غير موجود.")
        return

    await show_product_details_to_message(query.message, product.get("name"))


async def start_order_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_name = query.data.replace("order:", "", 1).strip()
    product = product_by_name(product_name)

    if product is None:
        await query.message.reply_text("❌ المنتج غير موجود.")
        return

    context.user_data["order_product"] = product_name
    context.user_data["order_step"] = "name"
    context.user_data["customer_chat_id"] = query.from_user.id
    context.user_data.pop("checkout_cart", None)

    await query.message.reply_text(
        f"🛒 طلب جديد: {product_name}\n\n"
        "من فضلك اكتب اسمك الكامل:"
    )


def add_product_to_cart(context: ContextTypes.DEFAULT_TYPE, product, unit="box"):
    cart = get_cart(context)
    product_name = product["name"]
    price = unit_price(product, unit)
    key = cart_key(product_name, unit)

    if key not in cart:
        cart[key] = {
            "name": product_name,
            "unit": unit,
            "unit_label": unit_label(unit),
            "qty": 0,
            "price": price,
            "price_text": format_price(price),
        }

    cart[key]["qty"] += 1
    return cart


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    idx = int(parts[2])
    unit = parts[3] if len(parts) > 3 else "box"

    product = product_by_index(idx)
    if product is None:
        await query.message.reply_text("❌ المنتج غير موجود.")
        return

    if unit == "strip" and not can_sell_strip(product):
        await query.message.reply_text("❌ هذا المنتج غير متاح للبيع بالشريط.")
        return

    cart = add_product_to_cart(context, product, unit)
    product_name = product["name"]

    await query.message.reply_text(
        f"✅ تمت إضافة {unit_label(unit)} من {product_name} إلى السلة.\n\n"
        f"عدد الوحدات في السلة: {cart_count(cart)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 عرض السلة", callback_data="cart:view")],
            [InlineKeyboardButton("➕ متابعة التسوق", callback_data="cart:continue")],
            [InlineKeyboardButton("✅ إتمام الطلب", callback_data="cart:checkout")],
        ]),
    )


async def view_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cart = get_cart(context)
    await query.message.reply_text(cart_text(cart), reply_markup=cart_keyboard(cart))


async def update_cart_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    _, action, idx_text = parts[:3]
    unit = parts[3] if len(parts) > 3 else "box"

    product = product_by_index(int(idx_text))
    if product is None:
        await query.message.reply_text("❌ المنتج غير موجود.")
        return

    product_name = product["name"]
    key = cart_key(product_name, unit)
    cart = get_cart(context)

    if key not in cart:
        await query.message.reply_text("❌ المنتج غير موجود في السلة.")
        return

    if action == "inc":
        cart[key]["qty"] += 1
    elif action == "dec":
        cart[key]["qty"] -= 1
        if cart[key]["qty"] <= 0:
            del cart[key]
    elif action == "remove":
        del cart[key]

    await query.message.reply_text(cart_text(cart), reply_markup=cart_keyboard(cart))


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["cart"] = {}
    await query.message.reply_text("🗑️ تم إفراغ السلة.", reply_markup=cart_keyboard({}))


async def continue_shopping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "اختر القسم الذي تريد متابعة التسوق منه:",
        reply_markup=ReplyKeyboardMarkup(products_keyboard, resize_keyboard=True),
    )


async def checkout_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cart = get_cart(context)
    if not cart:
        await query.message.reply_text("🛒 السلة فارغة، أضف منتجات أولاً.")
        return

    context.user_data["checkout_cart"] = True
    context.user_data["order_step"] = "name"
    context.user_data["customer_chat_id"] = query.from_user.id

    await query.message.reply_text(
        "✅ سنقوم بإتمام طلب السلة.\n\n"
        "من فضلك اكتب اسمك الكامل:"
    )


async def show_cart_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cart = get_cart(context)
    await update.message.reply_text(cart_text(cart), reply_markup=cart_keyboard(cart))


async def handle_checkout_interrupt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":")[1]

    if action == "shop":
        pending_text = context.user_data.pop("pending_shop_text", None)

        context.user_data.pop("order_step", None)
        context.user_data.pop("order_product", None)
        context.user_data.pop("checkout_cart", None)
        context.user_data.pop("customer_name", None)
        context.user_data.pop("customer_phone", None)
        context.user_data.pop("customer_address", None)

        await query.message.reply_text(
            "🛒 تم إيقاف إتمام الطلب مؤقتًا.\n"
            "سلتك محفوظة ويمكنك متابعة التسوق."
        )

        if pending_text:
            await route_shop_text_to_message(query.message, context, pending_text)
        else:
            await show_products_menu_to_message(query.message)

    elif action == "checkout":
        step = context.user_data.get("order_step", "name")

        if step == "name":
            await query.message.reply_text("✅ نكمل إتمام الطلب.\n\nمن فضلك اكتب اسمك الكامل:")
        elif step == "phone":
            await query.message.reply_text("✅ نكمل إتمام الطلب.\n\n📱 اكتب رقم الجوال:")
        elif step == "address":
            await query.message.reply_text("✅ نكمل إتمام الطلب.\n\n📍 اكتب عنوان التوصيل:")


async def handle_admin_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_CHAT_ID:
        await query.message.reply_text("❌ هذا الزر خاص بالإدارة فقط.")
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    _, action, order_id_text = parts
    order_id = int(order_id_text)

    status_map = {
        "confirm": ("confirmed", "✅ تم تأكيد طلبك، وسيتم تجهيزه الآن."),
        "prepare": ("preparing", "💊 طلبك الآن قيد التجهيز داخل الصيدلية."),
        "deliver": ("delivering", "🚚 طلبك خرج مع مندوب التوصيل."),
        "done": ("done", "📦 تم تسليم طلبك. شكرًا لاختياركم صيدليتك."),
        "cancel": ("cancelled", "❌ نعتذر، تم إلغاء طلبك."),
    }

    if action not in status_map:
        return

    new_status, customer_message = status_map[action]
    orders = load_orders()
    order = next((o for o in orders if o.get("id") == order_id), None)

    if not order:
        await query.message.reply_text("❌ لم يتم العثور على الطلب.")
        return

    order["status"] = new_status
    order["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_orders(orders)

    customer_chat_id = order.get("customer_chat_id")
    if customer_chat_id:
        try:
            await context.bot.send_message(
                chat_id=customer_chat_id,
                text=f"طلب رقم #{order_id}\n\n{customer_message}",
            )
        except Exception as e:
            print(f"خطأ إرسال تحديث الحالة للعميل: {e}")

    await query.message.edit_text(
        query.message.text + f"\n\n✅ تم تحديث الحالة إلى: {new_status}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    text = canonical_text(raw_text)
    print(f"USER_TEXT_RAW={repr(raw_text)} | CANONICAL={repr(text)}")

    if text == "💊 أدوية OTC" and not context.user_data.get("order_step"):
        context.user_data["search_step"] = True
        await show_otc_products_to_message(update.message)
        return

    if text == "💊 المنتجات" and not context.user_data.get("order_step"):
        await show_products_menu(update)
        return

    if text == "🔍 البحث عن منتج" and not context.user_data.get("order_step"):
        context.user_data["search_step"] = True
        await update.message.reply_text(
            "🔍 اكتب اسم المنتج أو جزءًا منه:\n\n"
            "مثال: Panadol / Brufen / فيتامين / صداع"
        )
        return

    if context.user_data.get("search_step"):
        if text in ["💊 المنتجات", "🔙 رجوع للمنتجات", "🔙 رجوع للقائمة الرئيسية", "🛒 السلة"]:
            context.user_data.pop("search_step", None)
        else:
            context.user_data.pop("search_step", None)
            await show_search_results_message(update.message, context, text)
            return

    if context.user_data.get("order_step") and is_navigation_or_product_text(text):
        context.user_data["pending_shop_text"] = text
        await update.message.reply_text(
            "⚠️ أنت الآن في مرحلة إتمام الطلب.\n\n"
            "ماذا تريد أن تفعل؟",
            reply_markup=checkout_interrupt_keyboard()
        )
        return

    if context.user_data.get("order_step") == "name":
        context.user_data["customer_name"] = text
        context.user_data["order_step"] = "phone"
        await update.message.reply_text("📱 اكتب رقم الجوال:")
        return

    if context.user_data.get("order_step") == "phone":
        context.user_data["customer_phone"] = text
        context.user_data["order_step"] = "address"
        await update.message.reply_text("📍 اكتب عنوان التوصيل:")
        return

    if context.user_data.get("order_step") == "address":
        context.user_data["customer_address"] = text

        order_id = create_order_id()
        customer_name = context.user_data.get("customer_name")
        customer_phone = context.user_data.get("customer_phone")
        customer_address = context.user_data.get("customer_address")
        customer_chat_id = context.user_data.get("customer_chat_id", update.effective_chat.id)

        cart = get_cart(context)
        is_cart_order = bool(context.user_data.get("checkout_cart")) and bool(cart)

        if is_cart_order:
            items = []
            items_text_lines = []
            for item in cart.values():
                qty = int(item.get("qty", 1))
                price = float(item.get("price", 0))
                subtotal = qty * price
                item_unit = item.get("unit", "box")
                item_unit_label = item.get("unit_label", unit_label(item_unit))
                items.append({
                    "name": item["name"],
                    "unit": item_unit,
                    "unit_label": item_unit_label,
                    "qty": qty,
                    "price": price,
                    "subtotal": subtotal,
                })
                items_text_lines.append(
                    f"• {item['name']} ({item_unit_label}) × {qty} = {format_price(subtotal)}"
                )

            total = cart_total(cart)
            product_name = "طلب متعدد المنتجات"
            items_text = "\n".join(items_text_lines)
        else:
            product_name = context.user_data.get("order_product")
            product = product_by_name(product_name) or {}
            price = product_box_price(product)
            items = [{
                "name": product_name,
                "unit": "box",
                "unit_label": "علبة",
                "qty": 1,
                "price": price,
                "subtotal": price
            }]
            total = price
            items_text = f"• {product_name} (علبة) × 1 = {format_price(price)}"

        order = {
            "id": order_id,
            "status": "new",
            "product": product_name,
            "items": items,
            "total": total,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_address": customer_address,
            "customer_chat_id": customer_chat_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        orders = load_orders()
        orders.append(order)
        save_orders(orders)
        append_order_to_google_sheets(order)

        order_message = (
            f"🛒 طلب جديد\n\n"
            f"🆔 رقم الطلب: #{order_id}\n"
            f"👤 الاسم: {customer_name}\n"
            f"📱 الجوال: {customer_phone}\n"
            f"📍 العنوان: {customer_address}\n\n"
            f"🛍️ المنتجات:\n{items_text}\n\n"
            f"💰 الإجمالي: {format_price(total)}"
        )

        admin_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تأكيد الطلب", callback_data=f"admin:confirm:{order_id}")],
            [InlineKeyboardButton("💊 قيد التجهيز", callback_data=f"admin:prepare:{order_id}")],
            [InlineKeyboardButton("🚚 خرج للتوصيل", callback_data=f"admin:deliver:{order_id}")],
            [InlineKeyboardButton("📦 تم التسليم", callback_data=f"admin:done:{order_id}")],
            [InlineKeyboardButton("❌ إلغاء الطلب", callback_data=f"admin:cancel:{order_id}")],
        ])

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=order_message,
                reply_markup=admin_buttons,
            )
        except Exception as e:
            print(f"خطأ إرسال الطلب للأدمن: {e}")

        await update.message.reply_text(
            f"✅ تم استلام طلبك بنجاح.\n\n"
            f"🆔 رقم الطلب: #{order_id}\n"
            f"💰 الإجمالي: {format_price(total)}\n"
            "سيتم التواصل معك لتأكيد الطلب."
        )

        context.user_data.pop("order_step", None)
        context.user_data.pop("order_product", None)
        context.user_data.pop("checkout_cart", None)
        context.user_data["cart"] = {}
        return

    product_names = [p["name"] for p in load_products()]

    if text == "💊 المنتجات":
        await show_products_menu(update)

    elif text == "🔍 البحث عن منتج":
        context.user_data["search_step"] = True
        await update.message.reply_text(
            "🔍 اكتب اسم المنتج أو جزءًا منه:\n\n"
            "مثال: Panadol / Brufen / فيتامين / صداع"
        )

    elif text == "💊 أدوية OTC":
        await show_otc_products(update)

    elif text in product_names:
        await show_product_details(update, text)

    elif text == "🛒 السلة":
        await show_cart_from_message(update, context)

    elif text.startswith("أريد "):
        product_name = text.replace("أريد ", "", 1).strip()

        if product_name in product_names:
            context.user_data["order_product"] = product_name
            context.user_data["order_step"] = "name"
            context.user_data["customer_chat_id"] = update.effective_chat.id
            context.user_data.pop("checkout_cart", None)

            await update.message.reply_text(
                f"🛒 طلب جديد: {product_name}\n\n"
                "من فضلك اكتب اسمك الكامل:"
            )
        else:
            await update.message.reply_text("❌ المنتج غير موجود.")

    elif text == "🔙 رجوع للمنتجات":
        await show_products_menu(update)

    elif text == "🔙 رجوع للقائمة الرئيسية":
        await start(update, context)

    elif text == "💪 مكملات غذائية":
        await update.message.reply_text("💪 مكملات غذائية\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "✨ مستحضرات تجميل":
        await update.message.reply_text("✨ مستحضرات تجميل\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "👶 مستلزمات أطفال":
        await update.message.reply_text("👶 مستلزمات أطفال\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "🩺 أجهزة طبية":
        await update.message.reply_text("🩺 أجهزة طبية\n\nقريبًا سنضيف المنتجات هنا.")

    elif text == "✨ العناية بالبشرة":
        await update.message.reply_text("✨ قريبًا: اكتشف روتين بشرتك حسب نوع البشرة والمشكلة.")

    elif text == "💇 العناية بالشعر":
        await update.message.reply_text("💇 قريبًا: تحليل مشكلة الشعر واقتراح المنتجات المناسبة.")

    elif text == "👶 الأم والطفل":
        await update.message.reply_text("👶 قسم الأم والطفل قيد التجهيز.")

    elif text == "🩺 اسأل الصيدلي":
        await update.message.reply_text("🩺 اكتب سؤالك هنا، وسيتم تحويله للصيدلي للرد عليك.")

    elif text == "🎁 العروض":
        await update.message.reply_text("🎁 لا توجد عروض مضافة حاليًا.")

    elif text == "📦 طلباتي":
        await update.message.reply_text("📦 قريبًا يمكنك متابعة طلباتك من هنا.")

    elif text == "📞 تواصل معنا":
        await update.message.reply_text(
            "📞 للتواصل معنا:\n"
            "واتساب: ضع رقمك هنا\n"
            "تيليجرام: @ضع_اسمك_هنا"
        )

    else:
        await update.message.reply_text("اكتب /start للعودة للقائمة الرئيسية.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"Unhandled error: {context.error}")
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)


def main():
    print("Starting bot...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(start_search_callback, pattern=r"^search:new$"))
    app.add_handler(CallbackQueryHandler(show_product_from_callback, pattern=r"^product:view:"))
    app.add_handler(CallbackQueryHandler(start_order_from_button, pattern=r"^order:"))
    app.add_handler(CallbackQueryHandler(handle_checkout_interrupt, pattern=r"^checkout_interrupt:"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern=r"^cart:add:"))
    app.add_handler(CallbackQueryHandler(view_cart_callback, pattern=r"^cart:view$"))
    app.add_handler(CallbackQueryHandler(update_cart_quantity, pattern=r"^cart:(inc|dec|remove):"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern=r"^cart:clear$"))
    app.add_handler(CallbackQueryHandler(continue_shopping, pattern=r"^cart:continue$"))
    app.add_handler(CallbackQueryHandler(checkout_cart, pattern=r"^cart:checkout$"))
    app.add_handler(CallbackQueryHandler(handle_admin_order_action, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
