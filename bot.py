import json
import os
import re
from datetime import datetime

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

from config import TOKEN

ADMIN_CHAT_ID = 1027957590
ORDERS_FILE = "orders.json"

main_keyboard = [
    ["💊 المنتجات", "✨ العناية بالبشرة"],
    ["💇 العناية بالشعر", "👶 الأم والطفل"],
    ["🩺 اسأل الصيدلي", "🎁 العروض"],
    ["🛒 السلة", "📦 طلباتي"],
    ["📞 تواصل معنا"],
]

products_keyboard = [
    ["💊 أدوية OTC", "💪 مكملات غذائية"],
    ["✨ مستحضرات تجميل", "👶 مستلزمات أطفال"],
    ["🩺 أجهزة طبية"],
    ["🔙 رجوع للقائمة الرئيسية"],
]


def load_products():
    with open("products.json", "r", encoding="utf-8") as file:
        return json.load(file)


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
        lines.append(f"{i}. {item['name']} × {qty} = {format_price(subtotal)}")

    lines.append("\n━━━━━━━━━━━━")
    lines.append(f"💰 الإجمالي: {format_price(cart_total(cart))}")
    return "\n".join(lines)


def cart_keyboard(cart):
    buttons = []

    for product_name in cart.keys():
        idx = product_index_by_name(product_name)
        if idx == -1:
            continue
        buttons.append([
            InlineKeyboardButton(f"➖ {product_name}", callback_data=f"cart:dec:{idx}"),
            InlineKeyboardButton("➕", callback_data=f"cart:inc:{idx}"),
            InlineKeyboardButton("🗑️", callback_data=f"cart:remove:{idx}"),
        ])

    buttons.append([InlineKeyboardButton("➕ متابعة التسوق", callback_data="cart:continue")])
    if cart:
        buttons.append([InlineKeyboardButton("✅ إتمام الطلب", callback_data="cart:checkout")])
        buttons.append([InlineKeyboardButton("🗑️ إفراغ السلة", callback_data="cart:clear")])

    return InlineKeyboardMarkup(buttons)


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
    await update.message.reply_text(
        "💊 قسم المنتجات\n\nاختر القسم الذي تريده:",
        reply_markup=ReplyKeyboardMarkup(products_keyboard, resize_keyboard=True),
    )


async def show_otc_products(update: Update):
    products = load_products()
    otc_products = [p["name"] for p in products if p.get("category") == "otc"]

    keyboard = [[name] for name in otc_products]
    keyboard.append(["🔙 رجوع للمنتجات"])

    await update.message.reply_text(
        "💊 أدوية OTC\n\nاختر المنتج:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def show_product_details(update: Update, product_name: str):
    product = product_by_name(product_name)

    if product is None:
        await update.message.reply_text("لم يتم العثور على المنتج.")
        return

    idx = product_index_by_name(product_name)

    caption = (
        f"💊 {product['name']}\n\n"
        f"💰 السعر: {product['price']}\n"
        f"📝 الاستخدام: {product['description']}"
    )

    product_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ أضف إلى السلة", callback_data=f"cart:add:{idx}")],
        [InlineKeyboardButton("🛒 عرض السلة", callback_data="cart:view")],
        [InlineKeyboardButton("⚡ اطلب الآن", callback_data=f"order:{product['name']}")],
    ])

    image_path = product.get("image", "")

    if image_path:
        try:
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=product_buttons,
                )
        except FileNotFoundError:
            await update.message.reply_text(
                caption + "\n\n⚠️ الصورة غير موجودة.",
                reply_markup=product_buttons,
            )
    else:
        await update.message.reply_text(caption, reply_markup=product_buttons)


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


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split(":")[-1])
    product = product_by_index(idx)
    if product is None:
        await query.message.reply_text("❌ المنتج غير موجود.")
        return

    cart = get_cart(context)
    product_name = product["name"]
    if product_name not in cart:
        cart[product_name] = {
            "name": product_name,
            "qty": 0,
            "price": parse_price(product.get("price", 0)),
            "price_text": str(product.get("price", "")),
        }
    cart[product_name]["qty"] += 1

    await query.message.reply_text(
        f"✅ تمت إضافة {product_name} إلى السلة.\n\n"
        f"عدد المنتجات في السلة: {cart_count(cart)}",
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

    _, action, idx_text = query.data.split(":")
    product = product_by_index(int(idx_text))
    if product is None:
        await query.message.reply_text("❌ المنتج غير موجود.")
        return

    product_name = product["name"]
    cart = get_cart(context)

    if product_name not in cart:
        await query.message.reply_text("❌ المنتج غير موجود في السلة.")
        return

    if action == "inc":
        cart[product_name]["qty"] += 1
    elif action == "dec":
        cart[product_name]["qty"] -= 1
        if cart[product_name]["qty"] <= 0:
            del cart[product_name]
    elif action == "remove":
        del cart[product_name]

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
    text = update.message.text.strip()

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
                items.append({
                    "name": item["name"],
                    "qty": qty,
                    "price": price,
                    "subtotal": subtotal,
                })
                items_text_lines.append(f"• {item['name']} × {qty} = {format_price(subtotal)}")

            total = cart_total(cart)
            product_name = "طلب متعدد المنتجات"
            items_text = "\n".join(items_text_lines)
        else:
            product_name = context.user_data.get("order_product")
            product = product_by_name(product_name) or {}
            price = parse_price(product.get("price", 0))
            items = [{"name": product_name, "qty": 1, "price": price, "subtotal": price}]
            total = price
            items_text = f"• {product_name} × 1 = {format_price(price)}"

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


def main():
    print("Starting bot...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(start_order_from_button, pattern=r"^order:"))
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern=r"^cart:add:"))
    app.add_handler(CallbackQueryHandler(view_cart_callback, pattern=r"^cart:view$"))
    app.add_handler(CallbackQueryHandler(update_cart_quantity, pattern=r"^cart:(inc|dec|remove):"))
    app.add_handler(CallbackQueryHandler(clear_cart, pattern=r"^cart:clear$"))
    app.add_handler(CallbackQueryHandler(continue_shopping, pattern=r"^cart:continue$"))
    app.add_handler(CallbackQueryHandler(checkout_cart, pattern=r"^cart:checkout$"))
    app.add_handler(CallbackQueryHandler(handle_admin_order_action, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
