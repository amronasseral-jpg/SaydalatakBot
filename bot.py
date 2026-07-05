import json
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from config import TOKEN

ADMIN_CHAT_ID = 1027957590

main_keyboard = [
    ["💊 المنتجات", "✨ العناية بالبشرة"],
    ["💇 العناية بالشعر", "👶 الأم والطفل"],
    ["🩺 اسأل الصيدلي", "🎁 العروض"],
    ["📦 طلباتي", "📞 تواصل معنا"]
]

products_keyboard = [
    ["💊 أدوية OTC", "💪 مكملات غذائية"],
    ["✨ مستحضرات تجميل", "👶 مستلزمات أطفال"],
    ["🩺 أجهزة طبية"],
    ["🔙 رجوع للقائمة الرئيسية"]
]


def load_products():
    with open("products.json", "r", encoding="utf-8") as file:
        return json.load(file)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏠 أهلاً بك في بوت صيدليتك\n\nاختر الخدمة التي تريدها:",
        reply_markup=ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)
    )


async def show_products_menu(update: Update):
    await update.message.reply_text(
        "💊 قسم المنتجات\n\nاختر القسم الذي تريده:",
        reply_markup=ReplyKeyboardMarkup(products_keyboard, resize_keyboard=True)
    )


async def show_otc_products(update: Update):
    products = load_products()
    otc_products = [p["name"] for p in products if p.get("category") == "otc"]

    keyboard = [[name] for name in otc_products]
    keyboard.append(["🔙 رجوع للمنتجات"])

    await update.message.reply_text(
        "💊 أدوية OTC\n\nاختر المنتج:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def show_product_details(update: Update, product_name: str):
    products = load_products()
    product = next((p for p in products if p.get("name") == product_name), None)

    if product is None:
        await update.message.reply_text("لم يتم العثور على المنتج.")
        return

    caption = (
        f"💊 {product['name']}\n\n"
        f"💰 السعر: {product['price']}\n"
        f"📝 الاستخدام: {product['description']}\n\n"
        f"للطلب اكتب: أريد {product['name']}"
    )

    image_path = product.get("image", "")

    if image_path:
        try:
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=caption)
        except FileNotFoundError:
            await update.message.reply_text(caption + "\n\n⚠️ الصورة غير موجودة.")
    else:
        await update.message.reply_text(caption)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # خطوات الطلب: الاسم ثم الجوال ثم العنوان
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

        order_message = (
            "🛒 طلب جديد\n\n"
            f"💊 المنتج: {context.user_data.get('order_product')}\n"
            f"👤 الاسم: {context.user_data.get('customer_name')}\n"
            f"📱 الجوال: {context.user_data.get('customer_phone')}\n"
            f"📍 العنوان: {context.user_data.get('customer_address')}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=order_message
            )
        except Exception as e:
            print(f"خطأ إرسال الطلب للأدمن: {e}")

        await update.message.reply_text(
            "✅ تم استلام طلبك بنجاح، سيتم التواصل معك لتأكيد الطلب."
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
