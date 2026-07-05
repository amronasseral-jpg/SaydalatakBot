import json
import os
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
    ["📦 طلباتي", "📞 تواصل معنا"],
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
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        await update.message.reply_text(
            caption + "\n⚠️ لم يتم العثور على صورة الترحيب images/welcome.png",
            reply_markup=reply_markup
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

    caption = (
        f"💊 {product['name']}\n\n"
        f"💰 السعر: {product['price']}\n"
        f"📝 الاستخدام: {product['description']}"
    )

    order_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 اطلب الآن", callback_data=f"order:{product['name']}")]
    ])

    image_path = product.get("image", "")

    if image_path:
        try:
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=order_button,
                )
        except FileNotFoundError:
            await update.message.reply_text(
                caption + "\n\n⚠️ الصورة غير موجودة.",
                reply_markup=order_button,
            )
    else:
        await update.message.reply_text(caption, reply_markup=order_button)


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

    await query.message.reply_text(
        f"🛒 طلب جديد: {product_name}\n\n"
        "من فضلك اكتب اسمك الكامل:"
    )


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
        product_name = context.user_data.get("order_product")
        customer_name = context.user_data.get("customer_name")
        customer_phone = context.user_data.get("customer_phone")
        customer_address = context.user_data.get("customer_address")
        customer_chat_id = context.user_data.get("customer_chat_id", update.effective_chat.id)

        order = {
            "id": order_id,
            "status": "new",
            "product": product_name,
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
            f"💊 المنتج: {product_name}\n"
            f"👤 الاسم: {customer_name}\n"
            f"📱 الجوال: {customer_phone}\n"
            f"📍 العنوان: {customer_address}"
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
            "سيتم التواصل معك لتأكيد الطلب."
        )

        context.user_data.clear()
        return

    product_names = [p["name"] for p in load_products()]

    if text == "💊 المنتجات":
        await show_products_menu(update)

    elif text == "💊 أدوية OTC":
        await show_otc_products(update)

    elif text in product_names:
        await show_product_details(update, text)

    elif text.startswith("أريد "):
        product_name = text.replace("أريد ", "", 1).strip()

        if product_name in product_names:
            context.user_data["order_product"] = product_name
            context.user_data["order_step"] = "name"
            context.user_data["customer_chat_id"] = update.effective_chat.id

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
    app.add_handler(CallbackQueryHandler(handle_admin_order_action, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
