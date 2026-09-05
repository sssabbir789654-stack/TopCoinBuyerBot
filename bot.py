import os
import sqlite3
from decimal import Decimal, InvalidOperation

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1943851828"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "sabbirvai007")
DB_PATH = os.getenv("DB_PATH", "bot.db")

COINS = [
    "Old Top Coin",
    "New Top Coin",
    "Niva Coin",
    "NS Coin",
]

SELL_COIN, SELL_AMOUNT, SELL_PAYMENT = range(3)
RATE_COIN, RATE_VALUE = range(3, 5)
BROADCAST_MESSAGE = 5


# =========================
# DATABASE
# =========================

def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rates (
            coin TEXT PRIMARY KEY,
            rate TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            coin TEXT NOT NULL,
            amount TEXT NOT NULL,
            total TEXT NOT NULL,
            payment TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for coin in COINS:
        cur.execute(
            "INSERT OR IGNORE INTO rates (coin, rate) VALUES (?, ?)",
            (coin, "0")
        )

    con.commit()
    con.close()


def save_user(user):
    con = db()

    con.execute("""
        INSERT INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
    """, (
        user.id,
        user.username or "",
        user.first_name or ""
    ))

    con.commit()
    con.close()


def get_rate(coin):
    con = db()

    row = con.execute(
        "SELECT rate FROM rates WHERE coin=?",
        (coin,)
    ).fetchone()

    con.close()

    if not row:
        return Decimal("0")

    return Decimal(row[0])


def set_rate(coin, rate):
    con = db()

    con.execute(
        "UPDATE rates SET rate=? WHERE coin=?",
        (str(rate), coin)
    )

    con.commit()
    con.close()


def create_order(user_id, username, coin, amount, total, payment):
    con = db()

    cur = con.cursor()

    cur.execute("""
        INSERT INTO orders
        (user_id, username, coin, amount, total, payment)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        coin,
        str(amount),
        str(total),
        payment
    ))

    order_id = cur.lastrowid

    con.commit()
    con.close()

    return order_id


def get_user_orders(user_id):
    con = db()

    rows = con.execute("""
        SELECT id, coin, amount, total, status, created_at
        FROM orders
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 20
    """, (user_id,)).fetchall()

    con.close()

    return rows


def get_pending_orders():
    con = db()

    rows = con.execute("""
        SELECT id, user_id, username, coin, amount,
               total, payment, created_at
        FROM orders
        WHERE status='pending'
        ORDER BY id ASC
    """).fetchall()

    con.close()

    return rows


def get_all_orders():
    con = db()

    rows = con.execute("""
        SELECT id, user_id, username, coin,
               amount, total, payment,
               status, created_at
        FROM orders
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()

    con.close()

    return rows


def get_order(order_id):
    con = db()

    row = con.execute("""
        SELECT id, user_id, username, coin,
               amount, total, payment,
               status, created_at
        FROM orders
        WHERE id=?
    """, (order_id,)).fetchone()

    con.close()

    return row


def update_order_status(order_id, status):
    con = db()

    cur = con.cursor()

    cur.execute("""
        UPDATE orders
        SET status=?
        WHERE id=? AND status='pending'
    """, (status, order_id))

    changed = cur.rowcount

    con.commit()
    con.close()

    return changed


# =========================
# KEYBOARDS
# =========================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🪙 Sell Coin",
                callback_data="sell"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Current Rate",
                callback_data="rates"
            ),
            InlineKeyboardButton(
                "📋 My Orders",
                callback_data="orders"
            )
        ],
        [
            InlineKeyboardButton(
                "📞 Support",
                url=f"https://t.me/{SUPPORT_USERNAME}"
            )
        ]
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚙️ Change Rate",
                callback_data="admin_rate"
            )
        ],
        [
            InlineKeyboardButton(
                "⏳ Pending Orders",
                callback_data="admin_pending"
            )
        ],
        [
            InlineKeyboardButton(
                "📋 Order History",
                callback_data="admin_history"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Broadcast",
                callback_data="admin_broadcast"
            )
        ]
    ])


def coin_keyboard(prefix):
    buttons = []

    for i, coin in enumerate(COINS):
        buttons.append([
            InlineKeyboardButton(
                coin,
                callback_data=f"{prefix}:{i}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "❌ Cancel",
            callback_data="cancel"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    save_user(user)

    text = (
        f"👋 Welcome {user.first_name}!\n\n"
        "🪙 Coin Buying Service\n\n"
        "আপনার Coin বিক্রি করতে নিচের "
        "\"Sell Coin\" বাটনে ক্লিক করুন।"
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=main_menu()
        )
    else:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=main_menu()
        )


# =========================
# CURRENT RATE
# =========================

async def show_rates(update, context):
    q = update.callback_query
    await q.answer()

    text = "📊 Current Coin Rate\n\n"

    for coin in COINS:
        rate = get_rate(coin)

        text += (
            f"🪙 {coin}\n"
            f"💰 1K = {rate} BDT\n\n"
        )

    await q.edit_message_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# SELL COIN
# =========================

async def sell_start(update, context):
    q = update.callback_query
    await q.answer()

    context.user_data.clear()

    await q.edit_message_text(
        "🪙 কোন Coin বিক্রি করতে চান?",
        reply_markup=coin_keyboard("sellcoin")
    )

    return SELL_COIN


async def sell_coin(update, context):
    q = update.callback_query
    await q.answer()

    index = int(q.data.split(":")[1])
    coin = COINS[index]

    rate = get_rate(coin)

    if rate <= 0:
        await q.edit_message_text(
            f"❌ {coin} এর Rate এখনো সেট করা হয়নি।\n\n"
            "কিছুক্ষণ পরে আবার চেষ্টা করুন।",
            reply_markup=main_menu()
        )

        return ConversationHandler.END

    context.user_data["coin"] = coin
    context.user_data["rate"] = str(rate)

    await q.edit_message_text(
        f"🪙 Selected: {coin}\n"
        f"💰 Rate: {rate} BDT / 1K\n\n"
        "এখন আপনি কত Coin বিক্রি করবেন?\n\n"
        "উদাহরণ:\n"
        "1000\n"
        "5000\n"
        "10000"
    )

    return SELL_AMOUNT


async def sell_amount(update, context):
    text = update.message.text.strip()

    try:
        amount = Decimal(text)
    except InvalidOperation:
        await update.message.reply_text(
            "❌ সঠিক সংখ্যা দিন।\n\n"
            "উদাহরণ: 1000"
        )

        return SELL_AMOUNT

    if amount <= 0:
        await update.message.reply_text(
            "❌ Amount অবশ্যই 0 এর বেশি হতে হবে।"
        )

        return SELL_AMOUNT

    if amount < 1000:
        await update.message.reply_text(
            "❌ Minimum amount 1000 Coin."
        )

        return SELL_AMOUNT

    rate = Decimal(
        context.user_data["rate"]
    )

    total = (amount / Decimal("1000")) * rate

    context.user_data["amount"] = str(amount)
    context.user_data["total"] = str(
        total.quantize(Decimal("0.01"))
    )

    await update.message.reply_text(
        f"🪙 Coin: {context.user_data['coin']}\n"
        f"🔢 Amount: {amount}\n"
        f"💰 Rate: {rate} BDT / 1K\n"
        f"💵 আপনি পাবেন: "
        f"{context.user_data['total']} BDT\n\n"
        "এখন আপনার Bkash/Nagad নম্বর "
        "অথবা প্রয়োজনীয় Payment Information পাঠান।"
    )

    return SELL_PAYMENT


async def sell_payment(update, context):
    payment = update.message.text.strip()

    if len(payment) < 3:
        await update.message.reply_text(
            "❌ সঠিক Payment Information দিন।"
        )

        return SELL_PAYMENT

    user = update.effective_user

    coin = context.user_data["coin"]
    amount = context.user_data["amount"]
    total = context.user_data["total"]

    order_id = create_order(
        user.id,
        user.username or "",
        coin,
        amount,
        total,
        payment
    )

    username = (
        f"@{user.username}"
        if user.username
        else "No Username"
    )

    admin_text = (
        "🔔 NEW COIN SELL ORDER\n\n"
        f"🆔 Order ID: #{order_id}\n"
        f"👤 User: {user.first_name}\n"
        f"🔗 Username: {username}\n"
        f"👤 User ID: {user.id}\n\n"
        f"🪙 Coin: {coin}\n"
        f"🔢 Amount: {amount}\n"
        f"💰 Payable: {total} BDT\n"
        f"💳 Payment: {payment}\n\n"
        "👇 Order Action:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"approve:{order_id}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"reject:{order_id}"
            )
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=keyboard
        )
    except Exception as e:
        print("Admin notification error:", e)

    await update.message.reply_text(
        f"✅ Order Submitted Successfully!\n\n"
        f"🆔 Order ID: #{order_id}\n"
        f"🪙 Coin: {coin}\n"
        f"🔢 Amount: {amount}\n"
        f"💵 Amount Receive: {total} BDT\n\n"
        "⏳ Admin আপনার Order যাচাই করবেন।",
        reply_markup=main_menu()
    )

    context.user_data.clear()

    return ConversationHandler.END


# =========================
# MY ORDERS
# =========================

async def show_orders(update, context):
    q = update.callback_query
    await q.answer()

    rows = get_user_orders(q.from_user.id)

    if not rows:
        await q.edit_message_text(
            "📋 আপনার কোনো Order নেই।",
            reply_markup=main_menu()
        )

        return

    text = "📋 Your Orders\n\n"

    for row in rows:
        order_id, coin, amount, total, status, created = row

        emoji = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌"
        }.get(status, "❓")

        text += (
            f"🆔 #{order_id}\n"
            f"🪙 {coin}\n"
            f"🔢 {amount} Coin\n"
            f"💰 {total} BDT\n"
            f"{emoji} {status.upper()}\n"
            f"📅 {created}\n\n"
        )

    await q.edit_message_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# ADMIN
# =========================

def is_admin(user_id):
    return user_id == ADMIN_ID


async def admin_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ Access Denied."
        )
        return

    await update.message.reply_text(
        "⚙️ Admin Panel",
        reply_markup=admin_menu()
    )


# =========================
# CHANGE RATE
# =========================

async def admin_rate_start(update, context):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return ConversationHandler.END

    await q.edit_message_text(
        "⚙️ কোন Coin-এর Rate পরিবর্তন করবেন?",
        reply_markup=coin_keyboard("admincoin")
    )

    return RATE_COIN


async def admin_select_coin(update, context):
    q = update.callback_query
    await q.answer()

    index = int(q.data.split(":")[1])
    coin = COINS[index]

    context.user_data["rate_coin"] = coin

    current = get_rate(coin)

    await q.edit_message_text(
        f"🪙 Coin: {coin}\n"
        f"📊 Current Rate: {current} BDT / 1K\n\n"
        "নতুন Rate লিখুন।\n\n"
        "উদাহরণ:\n"
        "2.50\n"
        "3\n"
        "4.25"
    )

    return RATE_VALUE


async def admin_set_rate(update, context):
    try:
        rate = Decimal(
            update.message.text.strip()
        )
    except InvalidOperation:
        await update.message.reply_text(
            "❌ সঠিক Rate দিন।"
        )

        return RATE_VALUE

    if rate < 0:
        await update.message.reply_text(
            "❌ Rate negative হতে পারে না।"
        )

        return RATE_VALUE

    coin = context.user_data["rate_coin"]

    set_rate(
        coin,
        rate.quantize(Decimal("0.01"))
    )

    await update.message.reply_text(
        f"✅ Rate Updated!\n\n"
        f"🪙 {coin}\n"
        f"💰 New Rate: {rate} BDT / 1K",
        reply_markup=admin_menu()
    )

    context.user_data.clear()

    return ConversationHandler.END


# =========================
# PENDING ORDERS
# =========================

async def admin_pending(update, context):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return

    rows = get_pending_orders()

    if not rows:
        await q.edit_message_text(
            "⏳ কোনো Pending Order নেই।",
            reply_markup=admin_menu()
        )

        return

    await q.edit_message_text(
        f"⏳ Pending Orders: {len(rows)}",
        reply_markup=admin_menu()
    )

    for row in rows:
        (
            order_id,
            user_id,
            username,
            coin,
            amount,
            total,
            payment,
            created
        ) = row

        text = (
            f"🆔 Order #{order_id}\n"
            f"👤 @{username or 'No Username'}\n"
            f"👤 ID: {user_id}\n"
            f"🪙 {coin}\n"
            f"🔢 {amount} Coin\n"
            f"💰 {total} BDT\n"
            f"💳 {payment}\n"
            f"📅 {created}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve:{order_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject:{order_id}"
                )
            ]
        ])

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            reply_markup=keyboard
        )


# =========================
# ORDER APPROVE / REJECT
# =========================

async def order_action(update, context):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return

    action, order_id_text = q.data.split(":")
    order_id = int(order_id_text)

    order = get_order(order_id)

    if not order:
        await q.edit_message_text(
            "❌ Order পাওয়া যায়নি।"
        )

        return

    (
        oid,
        user_id,
        username,
        coin,
        amount,
        total,
        payment,
        status,
        created
    ) = order

    if status != "pending":
        await q.edit_message_text(
            f"⚠️ Order #{order_id} already {status}."
        )

        return

    if action == "approve":
        new_status = "approved"
        emoji = "✅"

        message = (
            f"🎉 Your Order #{order_id} has been APPROVED!\n\n"
            f"🪙 {coin}\n"
            f"🔢 {amount} Coin\n"
            f"💰 Payment: {total} BDT"
        )

    else:
        new_status = "rejected"
        emoji = "❌"

        message = (
            f"❌ Your Order #{order_id} has been REJECTED.\n\n"
            f"🪙 {coin}\n"
            f"🔢 {amount} Coin"
        )

    changed = update_order_status(
        order_id,
        new_status
    )

    if changed == 0:
        await q.edit_message_text(
            "⚠️ Order status পরিবর্তন করা যায়নি।"
        )

        return

    await q.edit_message_text(
        f"{emoji} Order #{order_id} → "
        f"{new_status.upper()}"
    )

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=main_menu()
        )
    except Exception as e:
        print("User notification error:", e)


# =========================
# BROADCAST
# =========================

async def broadcast_start(update, context):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return ConversationHandler.END

    await q.edit_message_text(
        "📢 Broadcast Message লিখে পাঠান।\n\n"
        "Cancel করতে /cancel লিখুন।"
    )

    return BROADCAST_MESSAGE


async def broadcast_send(update, context):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    message = update.message.text

    con = db()

    users = con.execute(
        "SELECT user_id FROM users"
    ).fetchall()

    con.close()

    success = 0
    failed = 0

    for (user_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message
            )

            success += 1

        except Exception:
            failed += 1

    await update.message.reply_text(
        f"📢 Broadcast Complete\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}",
        reply_markup=admin_menu()
    )

    return ConversationHandler.END


# =========================
# ORDER HISTORY
# =========================

async def admin_history(update, context):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return

    rows = get_all_orders()

    if not rows:
        await q.edit_message_text(
            "📋 কোনো Order নেই।",
            reply_markup=admin_menu()
        )

        return

    text = "📋 Last 50 Orders\n\n"

    for row in rows:
        (
            order_id,
            user_id,
            username,
            coin,
            amount,
            total,
            payment,
            status,
            created
        ) = row

        text += (
            f"#{order_id} | {coin}\n"
            f"👤 {username or user_id}\n"
            f"🔢 {amount}\n"
            f"💰 {total} BDT\n"
            f"📌 {status.upper()}\n"
            f"📅 {created}\n\n"
        )

    await q.edit_message_text(
        text[:4000],
        reply_markup=admin_menu()
    )


# =========================
# CANCEL
# =========================

async def cancel(update, context):
    context.user_data.clear()

    if update.callback_query:
        await update.callback_query.answer()

        await update.callback_query.edit_message_text(
            "❌ Cancelled.",
            reply_markup=main_menu()
        )

    else:
        await update.message.reply_text(
            "❌ Cancelled.",
            reply_markup=main_menu()
        )

    return ConversationHandler.END


# =========================
# GENERIC CALLBACK
# =========================

async def callback_handler(update, context):
    q = update.callback_query

    if q.data == "rates":
        await show_rates(update, context)

    elif q.data == "orders":
        await show_orders(update, context)

    elif q.data == "admin_pending":
        await admin_pending(update, context)

    elif q.data == "admin_history":
        await admin_history(update, context)

    elif q.data == "cancel":
        await cancel(update, context)


# =========================
# MAIN
# =========================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # SELL CONVERSATION
    sell_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                sell_start,
                pattern=r"^sell$"
            )
        ],

        states={
            SELL_COIN: [
                CallbackQueryHandler(
                    sell_coin,
                    pattern=r"^sellcoin:\d+$"
                )
            ],

            SELL_AMOUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    sell_amount
                )
            ],

            SELL_PAYMENT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    sell_payment
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(
                cancel,
                pattern=r"^cancel$"
            )
        ]
    )

    # RATE CONVERSATION
    rate_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_rate_start,
                pattern=r"^admin_rate$"
            )
        ],

        states={
            RATE_COIN: [
                CallbackQueryHandler(
                    admin_select_coin,
                    pattern=r"^admincoin:\d+$"
                )
            ],

            RATE_VALUE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    admin_set_rate
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ]
    )

    # BROADCAST CONVERSATION
    broadcast_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                broadcast_start,
                pattern=r"^admin_broadcast$"
            )
        ],

        states={
            BROADCAST_MESSAGE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    broadcast_send
                )
            ]
        },

        fallbacks=[
            CommandHandler("cancel", cancel)
        ]
    )

    application.add_handler(sell_conversation)
    application.add_handler(rate_conversation)
    application.add_handler(broadcast_conversation)

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin_command)
    )

    application.add_handler(
        CommandHandler("cancel", cancel)
    )

    application.add_handler(
        CallbackQueryHandler(
            order_action,
            pattern=r"^(approve|reject):\d+$"
        )
    )

    application.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    print("Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
