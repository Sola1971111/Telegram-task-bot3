import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.ext import JobQueue
from telegram import ReplyKeyboardMarkup
from telegram.ext import CallbackContext
import datetime
import random
import asyncio  # Needed for async delays
import requests
import os


# Replace with your Bot API Token from BotFather
TOKEN = os.getenv("TOKEN")

# Telegram Group/Channel Link
GROUP_LINK = "https://t.me/taskpaybot12"  # Replace with your actual group link

# Admin ID (Replace with your own Telegram ID to receive withdrawal requests)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Replace this with your Telegram user ID

WITHDRAWAL_ADMIN_ID = int(os.getenv("WITHDRAWAL_ADMIN_ID", "0"))  # The admin who will handle withdrawals

# Initialize bot application
app = Application.builder().token(TOKEN).build()

# ✅ Initialize Job Queue
job_queue = app.job_queue

import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

DATABSE_URL = os.getenv("DATABASE_URL")

# ✅ Connect to PostgreSQL (Railway)
conn = psycopg2.connect(
    "DATABASE_URL",
    cursor_factory=RealDictCursor
)
cursor = conn.cursor()

# ✅ USERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    referrer_id BIGINT DEFAULT NULL,
    last_claim TEXT DEFAULT NULL,
    last_redeemed TEXT DEFAULT NULL,
    completed_tasks TEXT DEFAULT NULL
)
""")

# ✅ PROMO CODES
cursor.execute("""
CREATE TABLE IF NOT EXISTS promo_codes (
    code TEXT PRIMARY KEY,
    reward_amount INTEGER NOT NULL,
    max_redemptions INTEGER NOT NULL,
    current_redemptions INTEGER DEFAULT 0
)
""")

# ✅ WITHDRAWALS
cursor.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    amount INTEGER,
    bank_details TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ✅ COMPLETED PAYMENTS
cursor.execute("""
CREATE TABLE IF NOT EXISTS completed_payments (
    id SERIAL PRIMARY KEY,
    ad_id BIGINT,
    total_paid NUMERIC,
    completion_count INTEGER,
    referral_commission NUMERIC DEFAULT 0,
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# ✅ DEPOSITS
cursor.execute("""
CREATE TABLE IF NOT EXISTS deposits (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    proof TEXT NOT NULL,
    status TEXT DEFAULT 'pending'
)
""")

# ✅ DAILY WINS
cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_wins (
    date DATE PRIMARY KEY,
    count_2000 INTEGER DEFAULT 0
)
""")

# ✅ ADS
cursor.execute("""
CREATE TABLE IF NOT EXISTS ads (
    ad_id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    image_url TEXT NOT NULL,
    task_url TEXT NOT NULL,
    reward INTEGER NOT NULL
)
""")

# ✅ COMPLETED TASKS
cursor.execute("""
CREATE TABLE IF NOT EXISTS completed_tasks (
    user_id BIGINT,
    ad_id BIGINT,
    PRIMARY KEY (user_id, ad_id)
)
""")

# ✅ TASK COMPLETIONS
cursor.execute("""
CREATE TABLE IF NOT EXISTS task_completions (
    user_id BIGINT NOT NULL,
    task_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, task_id)
)
""")

# ✅ Save to DB
conn.commit()

# Logging setup
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def update_bot_description(context: ContextTypes.DEFAULT_TYPE):
    """Updates the bot's profile description with the total user count from PostgreSQL."""
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        result = cursor.fetchone()
        total_users = result['count'] if result else 0

        new_description = (
            f"🌍 {total_users} users are using this bot!\n\n"
            "Earn money by performing task with this bot"
        )

        await context.bot.set_my_description(new_description)
        print(f"✅ Bot description updated: {new_description}")

    except Exception as e:
        print(f"❌ Failed to update bot description: {e}")


# ---------------- START COMMAND ---------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    referrer_id = context.args[0] if context.args else None

    # Check if the user exists
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        # Insert new user
        cursor.execute(
            "INSERT INTO users (user_id, balance, referrals, referrer_id) VALUES (%s, %s, %s, %s)",
            (user_id, 0, 0, referrer_id if referrer_id and referrer_id.isdigit() else None)
        )
        conn.commit()

        # Update bot description with user count
        await update_bot_description(context)

        # Reward the referrer
        if referrer_id and referrer_id.isdigit():
            referrer_id = int(referrer_id)

            cursor.execute("SELECT * FROM users WHERE user_id = %s", (referrer_id,))
            referrer = cursor.fetchone()

            if referrer:
                cursor.execute(
                    "UPDATE users SET balance = balance + 100, referrals = referrals + 1 WHERE user_id = %s",
                    (referrer_id,)
                )
                conn.commit()

                # Notify the referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 Someone joined using your referral link! You earned 100 Naira."
                    )
                except:
                    pass

    # Generate referral link
    referral_link = f"https://t.me/Cooziepicks_bot?start={user_id}"

    # Inline keyboard
    keyboard = [
        [InlineKeyboardButton("📢 Join Our Official Channel", url="https://t.me/taskpaybot12")],
        [InlineKeyboardButton("📢 Perfom Tasks to earn", callback_data="whatsapp_task")],
        [InlineKeyboardButton("🎁 Claim Daily Bonus", callback_data="daily_bonus")],
        [InlineKeyboardButton("🎟️ Raffle Draw (Win up to ₦1 Million !💰)", callback_data="raffle_info")],
        [InlineKeyboardButton("🎡 Spin with ₦200 & Win Up To ₦20,000", callback_data="spin_wheel")],
        [InlineKeyboardButton("⚽ Get VIP Football Prediction", callback_data="football")],
        [InlineKeyboardButton("✍ Learn a Digital Skill", callback_data="learn_skill")],
        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance"),
         InlineKeyboardButton("💵 Withdraw", callback_data="withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Persistent keyboard
    persistent_keyboard = ReplyKeyboardMarkup(
        [["🏠 Home", "🎁 Claim Daily Bonus"],
         ["💰 Balance", "💵 Withdraw"],
         ["🎟️ 1 Million Draw", "🎡 Spin and Win"],
         ["✍ Learn a Digital Skill", "⚽VIP Football Tip"]],
        resize_keyboard=True, one_time_keyboard=False
    )

    await update.message.reply_text(
        f"🎉 Welcome! Share your referral link to earn 100 Naira per referral: \n\n🔗 {referral_link}\n\n Hold on the link to copy",
        reply_markup=reply_markup
    )

    await update.message.reply_text(
        "Press the 🏠 Main Menu button to go to home",
        reply_markup=persistent_keyboard
    )

app.add_handler(CommandHandler("start", start))



from datetime import datetime

async def check_today_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    today = datetime.datetime.now().strftime('%Y-%m-%d')  # Format: 2025-03-20

    # PostgreSQL-compatible DATE filter
    cursor.execute("""
        SELECT SUM(amount) FROM withdrawals
        WHERE DATE(created_at) = %s
    """, (today,))
    result = cursor.fetchone()
    total = result['sum'] if result and result['sum'] else 0

    await update.message.reply_text(f"📤 Total Withdrawals for Today ({today}): ₦{total}")

# Register the command
app.add_handler(CommandHandler("withdrawals_today", check_today_withdrawals))


async def football(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the raffle draw image, explanation, and payment button."""
    query = update.callback_query

    # Raffle Draw Image (Replace with your hosted image URL)
    football_image_url = "https://imgur.com/a/1w6acBr"

    # Raffle Draw Explanation
    football_text = (
        "95% ACCURATE FOOTBALL PREDICTION\n\n"
        "⚽ **Coozie Picks is the global leader in sports predictions. Bank with us and become one of the most successful sports bettors.** 🎟️\n\n"
        "Purchase a VIP ticket for as low as ₦1,000 and get our VIP predictions!\n\n"
        "✅ Our job is to help you make money from sports betting. Just sit back and watch your investment grow with our picks!\n\n"
        "🏆 Winners are announced on our Telegram channel daily!"
            )

    # Payment Link Button
    keyboard = [
        [InlineKeyboardButton("⚽ Get VIP Football Prediction", url="www.cooziepicks.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send Image + Explanation + Button
    await query.message.reply_photo(photo=football_image_url, caption=football_text, reply_markup=reply_markup, parse_mode="Markdown")

app.add_handler(CallbackQueryHandler(football, pattern="football"))


async def football_persist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the raffle draw image, explanation, and payment button."""
    query = update.callback_query

    # Raffle Draw Image (Replace with your hosted image URL)
    football_image_url = "https://imgur.com/a/1w6acBr"

    # Raffle Draw Explanation
    football_text = (
        "95% ACCURATE FOOTBALL PREDICTION\n\n"
        "⚽ **Coozie Picks is the global leader in sports predictions. Bank with us and become one of the most successful sports bettors.** 🎟️\n\n"
        "Purchase a VIP ticket for as low as ₦1,000 and get our VIP predictions!\n\n"
        "✅ Our job is to help you make money from sports betting. Just sit back and watch your investment grow with our picks!\n\n"
        "🏆 Winners are announced on our Telegram channel daily!"
            )

    # Payment Link Button
    keyboard = [
        [InlineKeyboardButton("⚽ Get VIP Football Prediction", url="www.cooziepicks.com")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send Image + Explanation + Button
    await update.effective_chat.send_photo(photo=football_image_url, caption=football_text, reply_markup=reply_markup, parse_mode="Markdown")

app.add_handler(MessageHandler(filters.Text("⚽VIP Football Tip"), football_persist))


CHANNEL_ID = "-1002437523390"

async def generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to generate codes.")
        return

    # Generate a 10-digit promo code
    new_code = str(random.randint(1000000000, 9999999999))

    # Store promo code in PostgreSQL
    cursor.execute("""
        INSERT INTO promo_codes (code, reward_amount, max_redemptions, current_redemptions)
        VALUES (%s, %s, %s, %s)
    """, (new_code, 1000, 1000, 0))
    conn.commit()

    # Promo code message
    message_text = (
        f"🎉 *NEW PROMO CODE GENERATED!* \n\n"
        f"🔹 *Code:* `{new_code}`\n"
        f"🎁 *Reward:* 1000 Naira\n"
        f"👥 *Available for:* 1000 users\n\n"
        f"To redeem, send this to the bot:\n"
        f"`/redeem {new_code}`"
    )

    # Send to channel
    await context.bot.send_message(chat_id=CHANNEL_ID, text=message_text, parse_mode="Markdown")

    # Notify admin
    await update.message.reply_text(
        f"✅ Promo code generated and sent to the channel!\n\nCode: `{new_code}`",
        parse_mode="Markdown"
    )

app.add_handler(CommandHandler("generate", generate_code))


async def redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text("⚠️ Please enter a code. Usage: `/redeem <code>`", parse_mode="Markdown")
        return

    entered_code = context.args[0]

    # Check if code exists and is still available
    cursor.execute("""
        SELECT reward_amount, max_redemptions, current_redemptions
        FROM promo_codes
        WHERE code = %s
    """, (entered_code,))
    code_info = cursor.fetchone()

    if not code_info:
        await update.message.reply_text("❌ Invalid or expired code.")
        return

    reward_amount = code_info['reward_amount']
    max_redemptions = code_info['max_redemptions']
    current_redemptions = code_info['current_redemptions']

    if current_redemptions >= max_redemptions:
        await update.message.reply_text("❌ This code has reached its maximum redemptions.")
        return

    # Check if the user already redeemed this code
    cursor.execute("""
        SELECT COUNT(*) FROM users
        WHERE user_id = %s AND last_redeemed = %s
    """, (user_id, entered_code))
    already_claimed = cursor.fetchone()['count']

    if already_claimed > 0:
        await update.message.reply_text("⚠️ You have already used this code.")
        return

    # Update user's balance and set last_redeemed
    cursor.execute("""
        UPDATE users
        SET balance = balance + %s, last_redeemed = %s
        WHERE user_id = %s
    """, (reward_amount, entered_code, user_id))

    # Increment the promo code redemption count
    cursor.execute("""
        UPDATE promo_codes
        SET current_redemptions = current_redemptions + 1
        WHERE code = %s
    """, (entered_code,))

    conn.commit()

    await update.message.reply_text(f"🎉 You have received *{reward_amount} Naira*! ✅", parse_mode="Markdown")

app.add_handler(CommandHandler("redeem", redeem_code))


async def learn_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✅ VTU Money Machine (VMM)", url="https://app.expertnaire.com/product/8031385747/8182410120")],
                [InlineKeyboardButton("👨🏼‍💻 Affiliate Marketing For Beginners (AMB)", url="https://app.expertnaire.com/product/8031385747/8011295469")],
                [InlineKeyboardButton("🖼️ Learn and Master Graphic Design", url="https://app.expertnaire.com/product/8031385747/7699274312")],
                [InlineKeyboardButton("📗 Amazon KDP Triple H Formula", url="https://app.expertnaire.com/product/8031385747/7714058088")],
                [InlineKeyboardButton("🌍 US Importation Masterclass", url="https://app.expertnaire.com/product/8031385747/6272148110")],
                [InlineKeyboardButton("📲 The Smartphone Video Editing", url="https://app.expertnaire.com/product/8031385747/7470337924")],
                [InlineKeyboardButton("▼ More", url="linktr.ee/Taskpay12")]
                ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text(
        "🚀 Pick a skill of your choice:", 
        reply_markup=reply_markup
    )

app.add_handler(CallbackQueryHandler(learn_skill, pattern="learn_skill"))


from datetime import datetime

async def spin_wheel_persist(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    user_name = update.effective_user.first_name
    spin_cost = 200
    max_2000_wins = 20
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # 🗑️ Delete previous spin-related messages
    for key in ["last_spin_message", "last_prize_message"]:
        if key in context.user_data:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=context.user_data[key])
            except:
                pass

    # Check balance
    cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()

    if not result or result["balance"] < spin_cost:
        await update.effective_chat.send_message("❌ You need at least 200 Naira to spin!\n\n Deposit to Spin")
        return

    # Deduct spin cost
    cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (spin_cost, user_id))
    conn.commit()

    # Check how many 2000 wins today
    cursor.execute("SELECT count_2000 FROM daily_wins WHERE date = %s", (today,))
    daily_win = cursor.fetchone()
    current_2000_wins = daily_win["count_2000"] if daily_win else 0

    # Rewards setup
    rewards = [0, 50, 150, 300, 2000]
    if current_2000_wins >= max_2000_wins:
        rewards.remove(2000)

    prize = random.choice(rewards)

    if prize == 2000:
        if daily_win:
            cursor.execute("UPDATE daily_wins SET count_2000 = count_2000 + 1 WHERE date = %s", (today,))
        else:
            cursor.execute("INSERT INTO daily_wins (date, count_2000) VALUES (%s, %s)", (today, 1))
        conn.commit()

    # 🌀 Spin Animation
    spin_steps = [
        "🎰 🎯 🔄 Spinning...",
        "🎰 🎉 🎯 Finalizing..."
    ]
    spin_message = await update.effective_chat.send_message(spin_steps[0])
    context.user_data["last_spin_message"] = spin_message.message_id

    for step in spin_steps[1:]:
        await asyncio.sleep(1)
        await spin_message.edit_text(step)

    if prize > 0:
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (prize, user_id))
        conn.commit()

    final_message_text = f"🎡 You spun the wheel!\n\n🎁 You won: {prize} Naira!\n\n"
    if prize == 0:
        final_message_text += "😢 Better luck next time!"
    else:
        final_message_text += "🎉 Congratulations! Your prize has been added to your balance."

    if prize == 2000:
        await broadcast_winner(context, user_id, user_name, prize)

    final_message = await update.effective_chat.send_message(final_message_text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Spin Again", callback_data="spin_wheel")]
    ]))
    context.user_data["last_prize_message"] = final_message.message_id

app.add_handler(MessageHandler(filters.Text("🎡 Spin and Win"), spin_wheel_persist))


async def raffle_info_persistent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the raffle draw image, explanation, and payment button."""
    query = update.callback_query

    # Raffle Draw Image (Replace with your hosted image URL)
    raffle_image_url = "https://imgur.com/a/VE0HJsK"

    # Raffle Draw Explanation
    explanation_text = (
        "TODAY MIGHT BE YOUR LUCKY CHANCE\n\n"
        "🎟️ **Welcome to the Raffle Draw!** 🎟️\n\n"
        "Purchase a ticket for just ₦500 stand a chance to win up to **₦1,000,000**!\n\n"
        "✅ The more tickets you buy, the higher your chances of winning!\n"
        "🎰 A random draw selects the winner.\n"
        "🏆 Winners are announced on our Telegram channel daily!\n\n"
        "Click the button below to purchase your raffle ticket now!"
    )

    # Payment Link Button
    keyboard = [
        [InlineKeyboardButton("🎟️ Get Raffle Draw Now", url="https://paystack.com/pay/raffedraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send Image + Explanation + Button
    await update.effective_chat.send_photo(photo=raffle_image_url, caption=explanation_text, reply_markup=reply_markup, parse_mode="Markdown")

app.add_handler(MessageHandler(filters.Text("🎟️ 1 Million Draw"), raffle_info_persistent))


async def learn_skill_persist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✅ VTU Money Machine (VMM)", url="https://app.expertnaire.com/product/8031385747/8182410120")],
                [InlineKeyboardButton("👨🏼‍💻 Affiliate Marketing For Beginners (AMB)", url="https://app.expertnaire.com/product/8031385747/8011295469")],
                [InlineKeyboardButton("🖼️ Learn and Master Graphic Design", url="https://app.expertnaire.com/product/8031385747/7699274312")],
                [InlineKeyboardButton("📗 Amazon KDP Triple H Formula", url="https://app.expertnaire.com/product/8031385747/7714058088")],
                [InlineKeyboardButton("🌍 US Importation Masterclass", url="https://app.expertnaire.com/product/8031385747/6272148110")],
                [InlineKeyboardButton("📲 The Smartphone Video Editing", url="https://app.expertnaire.com/product/8031385747/7470337924")],
                [InlineKeyboardButton("▼ More", url="linktr.ee/Taskpay12")]
                ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_chat.send_message(
        "🚀 Pick a skill of your choice:", 
        reply_markup=reply_markup
    )

app.add_handler(MessageHandler(filters.Text("✍ Learn a Digital Skill"), learn_skill_persist))


async def check_balance_persistent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles balance checking via persistent keyboard."""
    user_id = update.effective_chat.id

    # PostgreSQL query
    cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()

    if result:
        await update.effective_chat.send_message(f"💰 Your current balance: {result['balance']} Naira")
    else:
        await update.effective_chat.send_message("😕 You don't have a balance yet. Start referring or completing tasks!")

app.add_handler(MessageHandler(filters.Text("💰 Balance"), check_balance_persistent))


async def withdraw_persistent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles withdrawal requests and ensures users meet the referral requirement."""
    user_id = update.effective_chat.id

    # Get user's balance and referrals
    cursor.execute("SELECT balance, referrals FROM users WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()

    # Check if the user has a pending withdrawal
    cursor.execute("SELECT id FROM withdrawals WHERE user_id = %s AND status = 'pending'", (user_id,))
    pending_withdrawal = cursor.fetchone()

    if pending_withdrawal:
        await update.effective_chat.send_message(
            "❌ You already have a pending withdrawal.\n\nWait for it to be processed before requesting again."
        )
        return

    if user_data:
        balance = user_data["balance"]
        referrals = user_data["referrals"]

        required_referrals = 0  # Minimum referrals needed to withdraw
        referrals_needed = max(0, required_referrals - referrals)

        if referrals < required_referrals:
            await update.effective_chat.send_message(
                f"❌ You need at least {required_referrals} referrals to withdraw.\n\n"
                f"📌 You have {referrals} referrals.\n\n"
                f"👉 You need {referrals_needed} more referrals."
            )
            return

        if balance >= 700:
            context.user_data["withdraw"] = True
            context.user_data["withdraw_amount"] = balance

            await update.effective_chat.send_message(
                "✅ Send your bank details (Account Name, Bank Name, Account Number).\n"
                "Make sure you fill in the correct details."
            )
        else:
            await update.effective_chat.send_message(
                "❌ You need at least 700 Naira to withdraw.\n\nRefer to earn more."
            )
    else:
        await update.effective_chat.send_message("❌ User data not found. Try again later.")

app.add_handler(MessageHandler(filters.Text("💵 Withdraw"), withdraw_persistent))


async def claim_daily_bonus_persistent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the Daily Bonus button click."""
    user_id = update.effective_chat.id
    today = datetime.datetime.now().date()

    # Fetch the last claim date
    cursor.execute("SELECT last_claim FROM users WHERE user_id = %s", (user_id,))
    last_claim = cursor.fetchone()

    if last_claim and last_claim["last_claim"] == str(today):
        await update.effective_chat.send_message("❌ You have already claimed your daily bonus today!\n\nCome back tomorrow.")
        return

    # Reward the user
    bonus_amount = 50  # Adjust as needed
    cursor.execute(
        "UPDATE users SET balance = balance + %s, last_claim = %s WHERE user_id = %s",
        (bonus_amount, str(today), user_id)
    )
    conn.commit()

    await update.effective_chat.send_message(
        f"🎉 You received {bonus_amount} Naira as a daily bonus!\n\nCome back tomorrow."
    )

app.add_handler(MessageHandler(filters.Text("🎁 Claim Daily Bonus"), claim_daily_bonus_persistent))


async def add_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add a new ad task and broadcast it to users."""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to add ads.")
        return

    if len(context.args) < 4:
        await update.message.reply_text("⚠️ Usage: `/add_ad <title> | <image_url> | <task_url> | <reward>`")
        return

    try:
        title, image_url, task_url, reward = " ".join(context.args).split(" | ")
        title = title.replace("\\n", "\n")
        reward = int(reward)
    except ValueError:
        await update.message.reply_text("⚠️ Invalid format. Use: `/add_ad <title> | <image_url> | <task_url> | <reward>`")
        return

    # Insert into PostgreSQL ads table
    cursor.execute(
        "INSERT INTO ads (title, image_url, task_url, reward) VALUES (%s, %s, %s, %s) RETURNING ad_id",
        (title, image_url, task_url, reward)
    )
    ad_id = cursor.fetchone()["ad_id"]
    conn.commit()

    print(f"New Ad Created: {title} (ID: {ad_id})")

    # Prepare the ad message and buttons
    message = (
        f"💼 New Paid Task Available! ID:{ad_id}\n\n"
        f"{title}\n💰 Earn: {reward} Naira\n\n"
        f"📌 Complete the task and verify to claim your reward!"
    )
    keyboard = [
        [InlineKeyboardButton("🚀 Complete Task", url=task_url)],
        [InlineKeyboardButton("✅ Verify Task", callback_data=f"verify_task_{ad_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Fetch all users to send the ad
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        try:
            await context.bot.send_photo(
                chat_id=user["user_id"],
                photo=image_url,
                caption=message,
                reply_markup=reply_markup
            )
        except:
            pass  # Skip users who blocked the bot

    await update.message.reply_text("✅ Ad has been posted successfully!")

app.add_handler(CommandHandler("add_ad", add_ad))


async def verify_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when a user clicks the 'Verify Task' button"""
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data

    # Ensure callback data is in the correct format
    if not callback_data.startswith("verify_task_"):
        await query.answer("❌ Invalid verification request.", show_alert=True)
        return

    try:
        ad_id = int(callback_data.split("_")[-1])
    except ValueError:
        await query.answer("❌ Error processing task ID.", show_alert=True)
        return

    # Check if the ad still exists
    cursor.execute("SELECT title FROM ads WHERE ad_id = %s", (ad_id,))
    ad = cursor.fetchone()

    if not ad:
        await query.answer("🚫 Task no longer exists.", show_alert=True)
        return

    # Check if user already completed this task
    cursor.execute("SELECT * FROM completed_tasks WHERE user_id = %s AND ad_id = %s", (user_id, ad_id))
    existing = cursor.fetchone()

    if existing:
        await query.answer("❌ You have already verified this task and received your reward.", show_alert=True)
    else:
        # Set flag in context for awaiting photo upload
        context.user_data[f"awaiting_verification_{user_id}"] = ad_id
        await query.answer("📸 Please upload a picture as proof of completion.")
        await query.message.reply_text("✅ Upload a picture as proof, and your reward will be credited!")

app.add_handler(CallbackQueryHandler(verify_task, pattern="verify_task"))


async def handle_uploaded_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when a user uploads a picture for task verification and pays referral commission"""
    user_id = update.message.from_user.id
    ad_id = context.user_data.get(f"awaiting_verification_{user_id}")

    # Check if user actually clicked "Verify Task" first
    if ad_id:
        # Check if user has already completed this task
        cursor.execute("SELECT * FROM completed_tasks WHERE user_id = %s AND ad_id = %s", (user_id, ad_id))
        existing = cursor.fetchone()

        if existing:
            await update.message.reply_text("❌ You have already verified this task before.")
            return

        # Reward the user
        cursor.execute("SELECT reward FROM ads WHERE ad_id = %s", (ad_id,))
        ad = cursor.fetchone()

        if not ad:
            await update.message.reply_text("❌ Task not found!")
            return

        reward = ad["reward"]

        # Credit the user
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (reward, user_id))

        # Get referrer
        cursor.execute("SELECT referrer_id FROM users WHERE user_id = %s", (user_id,))
        ref_data = cursor.fetchone()

        referral_bonus = 0
        if ref_data and ref_data["referrer_id"]:
            referral_bonus = round(reward * 0.30)
            cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (referral_bonus, ref_data["referrer_id"]))
            try:
                await context.bot.send_message(
                    chat_id=ref_data["referrer_id"],
                    text=f"🎉 You earned ₦{referral_bonus} from your referral completing a task!"
                )
            except:
                pass  # ignore delivery errors

        # Save completed task
        cursor.execute("INSERT INTO completed_tasks (user_id, ad_id) VALUES (%s, %s)", (user_id, ad_id))
        conn.commit()

        await update.message.reply_text(f"🎉 Task Verified! You earned {reward} Naira.")
        context.user_data[f"awaiting_verification_{user_id}"] = None
    else:
        await update.message.reply_text("⚠️ Invalid Input.")

app.add_handler(MessageHandler(filters.PHOTO, handle_uploaded_photo))


async def check_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to check how many users have completed a specific ad task with details"""

    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/check_ad <ad_id>`", parse_mode="Markdown")
        return

    ad_id = context.args[0]

    # Fetch ad info
    cursor.execute("SELECT title, reward FROM ads WHERE ad_id = %s", (ad_id,))
    ad_info = cursor.fetchone()

    if not ad_info:
        await update.message.reply_text("❌ No ad found with this ID.")
        return

    title = ad_info["title"]
    reward = ad_info["reward"]

    # Fetch completion count
    cursor.execute("SELECT COUNT(*) FROM completed_tasks WHERE ad_id = %s", (ad_id,))
    completion_count = cursor.fetchone()["count"]

    message = (
        f"📊 **Ad Performance Report** 📊\n\n"
        f"📌 **{title}**\n"
        f"💰 Reward: {reward} Naira\n"
        f"👥 Completions: {completion_count}\n\n"
    )

    await update.message.reply_text(message, parse_mode="Markdown")

app.add_handler(CommandHandler("check_ad", check_ad))


async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows admin to delete a task while storing payout history"""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to delete tasks.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/delete_task <ad_id>`", parse_mode="Markdown")
        return

    ad_id = context.args[0]

    # Get ad details
    cursor.execute("SELECT title, reward FROM ads WHERE ad_id = %s", (ad_id,))
    ad = cursor.fetchone()

    if not ad:
        await update.message.reply_text("🚫 Ad not found or already deleted.")
        return

    title = ad["title"]
    reward = ad["reward"]

    # Count task completions
    cursor.execute("SELECT COUNT(*) FROM completed_tasks WHERE ad_id = %s", (ad_id,))
    completion_count = cursor.fetchone()["count"]

    total_paid = completion_count * reward

    # Store history
    cursor.execute("""
        INSERT INTO completed_payments (ad_id, total_paid, completion_count)
        VALUES (%s, %s, %s)
    """, (ad_id, total_paid, completion_count))
    conn.commit()

    # Delete the task
    cursor.execute("DELETE FROM ads WHERE ad_id = %s", (ad_id,))
    conn.commit()

    await update.message.reply_text(f"✅ Ad '{title}' deleted. Total paid: ₦{total_paid}.")

app.add_handler(CommandHandler("delete_task", delete_task))


async def check_ads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to check ads.")
        return

    # Get all ads and their completion counts
    cursor.execute("""
        SELECT ad_id, COUNT(user_id) AS count FROM completed_tasks GROUP BY ad_id
    """)
    ads_data = cursor.fetchall()

    if not ads_data:
        await update.message.reply_text("📢 No ad tasks have been completed yet.")
        return

    message = "📊 **Ad Performance Report** 📊\n\n"
    for row in ads_data:
        ad_id = row["ad_id"]
        count = row["count"]

        # Fetch ad details
        cursor.execute("SELECT title, reward FROM ads WHERE ad_id = %s", (ad_id,))
        ad_info = cursor.fetchone()

        if ad_info:
            title = ad_info["title"]
            reward = ad_info["reward"]
            message += f"📌 **{title}**\n💰 Reward: {reward} Naira\n👥 Completions: {count}\n\n"

    await update.message.reply_text(message, parse_mode="Markdown")

app.add_handler(CommandHandler("check_ads", check_ads))


async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a summary of admin earnings, including deleted tasks"""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to view admin reports.")
        return

    # Total earnings from deleted tasks (completed_payments table)
    cursor.execute("SELECT SUM(total_paid) FROM completed_payments")
    deleted_earnings = cursor.fetchone()["sum"] or 0

    # Total completions from deleted tasks
    cursor.execute("SELECT SUM(completion_count) FROM completed_payments")
    deleted_completions = cursor.fetchone()["sum"] or 0

    # Total completions from active tasks
    cursor.execute("SELECT COUNT(*) FROM completed_tasks")
    active_completions = cursor.fetchone()["count"] or 0

    # Estimate active task earnings by joining with ads
    cursor.execute("""
        SELECT SUM(a.reward)
        FROM completed_tasks ct
        JOIN ads a ON ct.ad_id = a.ad_id
    """)
    active_earnings = cursor.fetchone()["sum"] or 0

    total_earnings = active_earnings + deleted_earnings
    total_completions = active_completions + deleted_completions

    report = (
        f"📊 *Admin Report*\n\n"
        f"💰 *Total Earnings:* ₦{total_earnings}\n"
        f"📌 *Total Active Tasks Earnings:* ₦{active_earnings}\n"
        f"🗑️ *Total Deleted Task Earnings:* ₦{deleted_earnings}\n"
        f"✅ *Total Task Completions:* {total_completions}\n"
    )

    await update.message.reply_text(report, parse_mode="Markdown")

app.add_handler(CommandHandler("admin_report", admin_report))


async def claim_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the Daily Bonus button click."""
    query = update.callback_query
    user_id = query.from_user.id
    today = datetime.datetime.now().date()

    # Check last claim date
    cursor.execute("SELECT last_claim FROM users WHERE user_id = %s", (user_id,))
    last_claim = cursor.fetchone()

    if last_claim and last_claim["last_claim"] == str(today):
        await query.answer("❌ You have already claimed your daily bonus today!\n\nCome back tomorrow.", show_alert=True)
        return

    # Reward the user
    bonus_amount = 50
    cursor.execute(
        "UPDATE users SET balance = balance + %s, last_claim = %s WHERE user_id = %s",
        (bonus_amount, str(today), user_id)
    )
    conn.commit()

    await query.answer(f"🎉 You received {bonus_amount} Naira as a daily bonus!\n\nCome back tomorrow.", show_alert=True)

app.add_handler(CallbackQueryHandler(claim_daily_bonus, pattern="daily_bonus"))


async def raffle_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the raffle draw image, explanation, and payment button."""
    query = update.callback_query

    # Raffle Draw Image (Replace with your hosted image URL)
    raffle_image_url = "https://imgur.com/a/VE0HJsK"

    # Raffle Draw Explanation
    explanation_text = (
        "TODAY MIGHT BE YOUR LUCKY CHANCE\n\n"
        "🎟️ **Welcome to the Raffle Draw!** 🎟️\n\n"
        "Purchase a ticket for just ₦500 stand a chance to win up to **₦1,000,000**!\n\n"
        "✅ The more tickets you buy, the higher your chances of winning!\n"
        "🎰 A random draw selects the winner.\n"
        "🏆 Winners are announced on our Telegram channel daily!\n\n"
        "Click the button below to purchase your raffle ticket now!"
    )

    # Payment Link Button
    keyboard = [
        [InlineKeyboardButton("🎟️ Get Raffle Draw Now", url="https://paystack.com/pay/raffedraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send Image + Explanation + Button
    await query.message.reply_photo(photo=raffle_image_url, caption=explanation_text, reply_markup=reply_markup, parse_mode="Markdown")

app.add_handler(CallbackQueryHandler(raffle_info, pattern="raffle_info"))


async def send_raffle_post(context: ContextTypes.DEFAULT_TYPE):
    """Sends the raffle draw image, explanation, and button to the Telegram channel."""
    CHANNEL_ID = "-1002437523390"

    raffle_image_url = "https://imgur.com/a/VE0HJsK"

    explanation_text = (
        "🎟️ **Join Today's Raffle Draw!** 🎟️\n\n"
        "💰 Purchase a ticket for ₦500 and stand a chance to win **₦1,000,000**!\n"
        "🎰 The more tickets you buy, the higher your chances of winning!\n"
        "🎰 A random draw selects the winner.\n"
        "🏆 Winners are announced daily!\n\n"
        "**Click the button below to purchase your raffle ticket now!**"
    )

    keyboard = [
        [InlineKeyboardButton("🎟️ Get Raffle Draw Now", url="https://paystack.com/pay/raffedraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=raffle_image_url,
            caption=explanation_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        print("✅ Raffle Draw post sent successfully!")
    except Exception as e:
        print(f"❌ Error sending message to channel: {e}")

    # Send to all bot users (PostgreSQL version)
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        try:
            await context.bot.send_photo(
                chat_id=user["user_id"],
                photo=raffle_image_url,
                caption=explanation_text,
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Could not send to {user['user_id']}: {e}")


async def post_raffle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to send the raffle post to the channel."""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to send a raffle post.")
        return

    CHANNEL_ID = "-1002437523390"  # Replace with your actual channel ID

    # Raffle Draw Image
    raffle_image_url = "https://imgur.com/a/VE0HJsK"

    # Raffle Draw Explanation
    explanation_text = (
        "🎟️ Join Today's Raffle Draw! 🎟️\n\n"
        "💰 Purchase a ticket for ₦500 and stand a chance to win ₦1,000,000!\n"
        "🎰 The more tickets you buy, the higher your chances of winning!\n"
        "🎰 A random draw selects the winner.\n"
        "🏆 Winners are announced daily!\n\n"
        "Click the button below to purchase your raffle ticket now!"
    )

    keyboard = [
        [InlineKeyboardButton("🎟️ Get Raffle Draw Now", url="https://paystack.com/pay/raffedraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send to Channel
    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=raffle_image_url,
            caption=explanation_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        print("✅ Raffle Draw post sent successfully to the channel!")
    except Exception as e:
        print(f"❌ Error sending message to channel: {e}")

    # Send to all bot users (PostgreSQL)
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        try:
            await context.bot.send_photo(
                chat_id=user["user_id"],
                photo=raffle_image_url,
                caption=explanation_text,
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Could not send to {user['user_id']}: {e}")

    await update.message.reply_text("✅ Raffle draw post has been sent to the channel!")

app.add_handler(CommandHandler("post_raffle", post_raffle))


import random
import asyncio
import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram import Update

import random
import asyncio
import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram import Update

async def spin_wheel(update: Update, context: CallbackContext):
    """Handles the Spin & Win feature, removes previous messages when spinning again."""
    query = update.callback_query
    user_id = query.from_user.id
    user_name = query.from_user.first_name

    spin_cost = 200
    max_2000_wins = 20
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # 🗑️ Delete previous messages
    for key in ["last_spin_message", "last_prize_message"]:
        if key in context.user_data:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=context.user_data[key])
            except:
                pass

    # Check user balance
    cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
    balance = cursor.fetchone()

    if not balance or balance["balance"] < spin_cost:
        await query.answer("❌ You need at least 200 Naira to spin!\n\n Deposit to Spin", show_alert=True)
        return

    # Deduct spin cost
    cursor.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s", (spin_cost, user_id))
    conn.commit()

    # Check ₦2000 wins today
    cursor.execute("SELECT count_2000 FROM daily_wins WHERE date = %s", (today,))
    daily_win = cursor.fetchone()
    current_2000_wins = daily_win["count_2000"] if daily_win else 0

    rewards = [0, 50, 150, 300, 2000]
    if current_2000_wins >= max_2000_wins:
        rewards.remove(2000)

    prize = random.choice(rewards)

    # Update ₦2000 win count
    if prize == 2000:
        if daily_win:
            cursor.execute("UPDATE daily_wins SET count_2000 = count_2000 + 1 WHERE date = %s", (today,))
        else:
            cursor.execute("INSERT INTO daily_wins (date, count_2000) VALUES (%s, %s)", (today, 1))
        conn.commit()

    # Spin animation
    spin_steps = [
        "🎰 🎯 🔄 Spinning...",
        "🎰 🎉 🎯 Finalizing..."
    ]
    spin_message = await query.message.reply_text(spin_steps[0])
    context.user_data["last_spin_message"] = spin_message.message_id

    for step in spin_steps[1:]:
        await asyncio.sleep(1)
        await spin_message.edit_text(step)

    # Credit prize
    if prize > 0:
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (prize, user_id))
        conn.commit()

    # Final message
    final_message_text = f"🎡 You spun the wheel!\n\n🎁 You won: {prize} Naira!\n\n"
    if prize == 0:
        final_message_text += "😢 Better luck next time!"
    else:
        final_message_text += "🎉 Congratulations! Your prize has been added to your balance."

    if prize == 2000:
        await broadcast_winner(context, user_id, user_name, prize)

    final_message = await query.message.reply_text(
        final_message_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Spin Again", callback_data="spin_wheel")]
        ])
    )
    context.user_data["last_prize_message"] = final_message.message_id

app.add_handler(CallbackQueryHandler(spin_wheel, pattern="spin_wheel"))


async def reset_daily_wins(context: ContextTypes.DEFAULT_TYPE):
    """Resets the daily ₦2000 win count at midnight."""
    cursor.execute("DELETE FROM daily_wins")
    conn.commit()
    print("🔄 Daily ₦2000 spin wins have been reset!")

# Schedule the reset function to run daily at midnight
job_queue.run_daily(reset_daily_wins, time=datetime.time(0, 0, 0))


async def broadcast_winner(context: ContextTypes.DEFAULT_TYPE, winner_id: int, user_name: str, amount: int):
    """Broadcasts a message to all users when someone wins ₦2000, but shows 'You' to the winner."""
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        recipient_id = user["user_id"]

        if recipient_id == winner_id:
            message = (
                f"🎉 You just won {amount} Naira! 🎰💰\n\n"
                "🔥 Keep spinning for more wins!"
            )
            keyboard = [[InlineKeyboardButton("🔄 Spin Again", callback_data="spin_wheel")]]
        else:
            message = (
                f"🎉 {user_name} just won {amount} Naira! 🎰💰\n\n"
                "🔥 Will you be the next big winner? Spin now!"
            )
            keyboard = [[InlineKeyboardButton("🎡 Spin Now", callback_data="spin_wheel")]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(chat_id=recipient_id, text=message, reply_markup=reply_markup)
        except:
            pass  # Ignore users who blocked the bot


async def return_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the persistent '🏠 Main Menu' button click and redirects to /start."""
    await start(update, context)  # Call the /start function to reload the menu

app.add_handler(MessageHandler(filters.Text("🏠 Home"), return_to_main_menu))


# Store user interaction count (in-memory)
user_interactions = {}

async def check_and_resend_keyboard(update: Update, context: CallbackContext):
    """Resends the persistent button if the user has interacted too many times without seeing it."""
    if not update.message:
        return  # Prevent crash if update is not a message

    user_id = update.effective_chat.id
    user_interactions[user_id] = user_interactions.get(user_id, 0) + 1

    if user_interactions[user_id] >= 5:
        keyboard = [["🔄 Return to Menu"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

        await update.message.reply_text("\u200B", reply_markup=reply_markup)  # \u200B = invisible character
        user_interactions[user_id] = 0  # Reset counter


# ---------------- BALANCE COMMAND ---------------- #
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks the user's balance and displays it as an alert."""
    query = update.callback_query
    user_id = query.from_user.id

    cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
    balance = cursor.fetchone()

    if balance:
        await query.answer(f"💰 Your current balance: {balance['balance']} Naira", show_alert=True)
    else:
        await query.answer("😕 You don't have a balance yet. Start referring or completing tasks!", show_alert=True)


WHATSAPP_LINK = "https://t.me/nigeriap2pcommunity"  # Replace with your WhatsApp group link

async def whatsapp_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📢 Join Group (Nigeria P2P Center)", url=WHATSAPP_LINK)],
        [InlineKeyboardButton("📢 Join Group (Sport Betting Channel)", url="https://t.me/+Wckxjj2O_SgxOGU0")],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_task_2")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text(
        "🎯 Join the Telegram Channels to earn 150 Naira!",
        reply_markup=reply_markup
    )

app.add_handler(CallbackQueryHandler(whatsapp_task, pattern="whatsapp_task"))


async def verify_task_2(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    # Check if task 2 has already been completed
    cursor.execute('SELECT 1 FROM task_completions WHERE user_id = %s AND task_id = 1', (user_id,))
    if cursor.fetchone():
        await query.answer("❌ You have already completed this Task.", show_alert=True)
        return

    # Get current balance
    cursor.execute('SELECT balance FROM users WHERE user_id = %s', (user_id,))
    row = cursor.fetchone()
    current_balance = row["balance"] if row else 0

    new_balance = current_balance + 150
    cursor.execute('UPDATE users SET balance = %s WHERE user_id = %s', (new_balance, user_id))

    # Mark Task 2 as completed
    cursor.execute('INSERT INTO task_completions (user_id, task_id) VALUES (%s, 1)', (user_id,))
    conn.commit()

    await query.answer("🎯 Task 2 completed! You earned 150 Naira.", show_alert=True)

app.add_handler(CallbackQueryHandler(verify_task_2, pattern="^verify_task_2$"))


# ---------------- WITHDRAW SYSTEM ---------------- #
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles withdrawal requests and ensures users meet the referral requirement."""
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id

    # Get user's balance and referrals
    cursor.execute("SELECT balance, referrals FROM users WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()

    # Check if the user has a pending withdrawal
    cursor.execute("SELECT id FROM withdrawals WHERE user_id = %s AND status = 'pending'", (user_id,))
    pending_withdrawal = cursor.fetchone()

    if pending_withdrawal:
        await query.answer(
            "❌ You already have a pending withdrawal. \n\nWait for it to be processed before requesting again.",
            show_alert=True
        )
        return

    if user_data:
        balance = user_data["balance"]
        referrals = user_data["referrals"]
        required_referrals = 0
        referrals_needed = max(0, required_referrals - referrals)

        if referrals < required_referrals:
            await query.answer(
                f"❌ You need at least {required_referrals} referrals to withdraw.\n\n"
                f"📌 You have {referrals} referrals.\n\n"
                f"👉 You need {referrals_needed} more referrals.",
                show_alert=True
            )
            return

        if balance >= 700:
            context.user_data["withdraw"] = True
            context.user_data["withdraw_amount"] = balance

            await query.message.reply_text(
                "✅ Send your bank details in this format:\n"
                "Account Name,\nBank Name,\nAccount Number.\n\n"
                "Make sure you fill in the correct details."
            )
        else:
            await query.answer(
                "❌ You need at least 700 Naira to withdraw.\n\nRefer to earn more.",
                show_alert=True
            )
    else:
        await query.answer("❌ User data not found. Try again later.", show_alert=True)


async def process_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    text = update.message.text.strip()

    # Ensure user is in withdrawal process
    if "withdraw" not in context.user_data or not context.user_data["withdraw"]:
        return  

    withdraw_amount = context.user_data["withdraw_amount"]

    # Store withdrawal request in DB
    cursor.execute("""
        INSERT INTO withdrawals (user_id, amount, bank_details, status)
        VALUES (%s, %s, %s, 'pending')
    """, (user_id, withdraw_amount, text))
    conn.commit()

    # Reset user's balance to 0 after withdrawal
    cursor.execute("UPDATE users SET balance = 0 WHERE user_id = %s", (user_id,))
    conn.commit()

    # Notify user
    await update.message.reply_text(
        f"✅ Your withdrawal request of {withdraw_amount} Naira has been received.\n\n📌 *Bank Details:* {text}\n\n🔄 *Awaiting Admin Approval...*",
        parse_mode="Markdown"
    )

    # Notify Admin with Approve & Reject Buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=WITHDRAWAL_ADMIN_ID,
        text=(
            f"🔔 *Withdrawal Request* 🔔\n\n"
            f"👤 *User ID:* `{user_id}`\n"
            f"💰 *Amount:* {withdraw_amount} Naira\n"
            f"🏦 *Bank Details:* `{text}`\n\n"
            f"📌 *Action Required:*"
        ),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    # Clear withdrawal state
    context.user_data["withdraw"] = False
    context.user_data["withdraw_amount"] = 0


app.add_handler(CommandHandler("withdraw", withdraw))  # Make sure this only triggers the start
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_withdrawal))


async def handle_withdrawal_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id

    if admin_id != WITHDRAWAL_ADMIN_ID:
        await query.answer("❌ You are not authorized to perform this action.", show_alert=True)
        return

    data = query.data
    action, user_id = data.split("_")
    user_id = int(user_id)

    # Fetch withdrawal details
    cursor.execute("SELECT amount FROM withdrawals WHERE user_id = %s AND status = 'pending'", (user_id,))
    withdrawal = cursor.fetchone()

    if not withdrawal:
        await query.answer("⚠️ Withdrawal already processed or does not exist.", show_alert=True)
        return

    withdraw_amount = withdrawal["amount"]

    if action == "approve":
        # Mark as processed
        cursor.execute("UPDATE withdrawals SET status = 'processed' WHERE user_id = %s", (user_id,))
        conn.commit()

        # Notify User
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ *Withdrawal Approved!* 🎉\n\n💰 *Amount:* {withdraw_amount} Naira has been successfully processed. Thank you!",
            parse_mode="Markdown"
        )

        await query.answer("✅ Withdrawal approved!", show_alert=True)
        await query.message.edit_text(f"✅ Withdrawal for `{user_id}` has been processed.")

    elif action == "reject":
        # Refund the user
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (withdraw_amount, user_id))
        cursor.execute("UPDATE withdrawals SET status = 'rejected' WHERE user_id = %s", (user_id,))
        conn.commit()

        # Notify User
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ *Withdrawal Rejected!* Check the Bank Details you provided.\n\n💰 *Amount Refunded:* {withdraw_amount} Naira.",
            parse_mode="Markdown"
        )

        await query.answer("❌ Withdrawal rejected & amount refunded!", show_alert=True)
        await query.message.edit_text(f"❌ Withdrawal for `{user_id}` was rejected & refunded.")

app.add_handler(CallbackQueryHandler(handle_withdrawal_decision, pattern="^(approve|reject)_"))


import datetime
from telegram.ext import JobQueue

async def deduct_weekly_task_fee(context: ContextTypes.DEFAULT_TYPE):
    """Deducts a weekly task fee from all users and notifies them."""
    cursor.execute("SELECT user_id, balance FROM users")
    users = cursor.fetchall()

    deduction_amount = 50  # Amount to deduct weekly

    for user in users:
        user_id = user["user_id"]
        balance = user["balance"]

        if balance >= deduction_amount:
            cursor.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id = %s",
                (deduction_amount, user_id)
            )
            conn.commit()
            message = (
                "🔔 Weekly Task Fee Deducted 🔔\n\n"
                "💵 50 Naira has been deducted from your balance."
            )
        else:
            message = (
                "⚠️ Insufficient Balance ⚠️\n\n"
                "You need at least 50 Naira for the weekly task fee."
            )

        try:
            await context.bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            print(f"Could not send message to {user_id}: {e}")


# Start job queue
job_queue = app.job_queue

# Run deduction every 7 days (604800 seconds)
job_queue.run_repeating(deduct_weekly_task_fee, interval=604800, first=datetime.timedelta(days=7))


async def manual_deduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually deducts the weekly task fee when an admin runs /deduct."""
    user_id = update.message.chat_id

    if user_id == ADMIN_ID:
        await deduct_weekly_task_fee(context)
        await update.message.reply_text("✅ Weekly deduction has been manually triggered!")
    else:
        await update.message.reply_text("⛔ You are not authorized to run this command.")


# Register the manual command handler
app.add_handler(CommandHandler("deduct", manual_deduct))


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to send a broadcast.")
        return

    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("⚠️ Usage: `/broadcast <your message>`")
        return

    # Get all users
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user["user_id"]
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
        except:
            pass  # Ignore users who blocked the bot or removed it

    await update.message.reply_text("✅ Broadcast sent to all users!")

app.add_handler(CommandHandler("broadcast", broadcast))


async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT COUNT(*) AS count FROM users")
    result = cursor.fetchone()
    total_users = result["count"] if result else 0

    await update.message.reply_text(f"📊 Total Users: {total_users}")

app.add_handler(CommandHandler("usercount", user_count))


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the top 10 users with the highest referrals."""
    query = update.callback_query

    cursor.execute("SELECT user_id, referrals FROM users ORDER BY referrals DESC LIMIT 10")
    top_users = cursor.fetchall()

    message = "🏆 Referral Leaderboard For This Week\n\n"
    if not top_users:
        message += "No referrals yet. Start referring to appear on the leaderboard!"
    else:
        for rank, user in enumerate(top_users, start=1):
            message += f"🥇 {rank}. User {user['user_id']} - {user['referrals']} referrals\n"

    # Send the message to the channel
    await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="Markdown")

app.add_handler(CommandHandler("leaderboard", leaderboard))


async def reward_top_referrers(context: ContextTypes.DEFAULT_TYPE):
    """Automatically rewards the top 3 referrers every week and resets referral counts."""
    cursor.execute("SELECT user_id, referrals FROM users ORDER BY referrals DESC LIMIT 3")
    top_users = cursor.fetchall()

    rewards = [25000, 10000, 5000]  # 1st, 2nd, 3rd place rewards

    for i, user in enumerate(top_users):
        user_id = user["user_id"]
        referrals = user["referrals"]
        amount = rewards[i]

        # Credit the reward
        cursor.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()

        # Notify winner
        message = (
            f"🎉 Congratulations! You were ranked #{i+1} in the referral leaderboard!\n\n"
            f"🏆 You've won {amount} Naira!\n\nKeep inviting for more rewards!"
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
        except:
            pass  # Ignore if user has blocked the bot

    # Reset referral counts
    cursor.execute("UPDATE users SET referrals = 0")
    conn.commit()

    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text="✅ Top referrers have been rewarded and all referrals have been reset!"
    )


async def manual_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually rewards the top 3 referrers when the admin runs /reward."""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to run this command.")
        return

    await reward_top_referrers(context)  # Call the reward function
    await update.message.reply_text("✅ Rewards have been manually distributed!")

app.add_handler(CommandHandler("reward", manual_reward))



async def give_all_users_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to run this command.")
        return

    # Update all users' balance (+500 Naira)
    cursor.execute("UPDATE users SET balance = balance + 500")
    conn.commit()

    # Get all users' IDs
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    message = "🎉 Congratulations! You have received 500 Naira as a special bonus!"
    sent_count = 0

    for user in users:
        user_id = user["user_id"]
        try:
            await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
            sent_count += 1
        except Exception as e:
            print(f"Failed to send message to {user_id}: {e}")

    await update.message.reply_text(f"✅ Bonus added and message sent to {sent_count} users!")

app.add_handler(CommandHandler("give_bonus", give_all_users_bonus))


# ---------------- BUTTON HANDLER ---------------- #
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "check_balance":
        await check_balance(update, context)
    elif data == "complete_task":
        await complete_task(update, context)
    elif data == "withdraw":
        await withdraw(update, context)
    elif data == "raffle_info":
        await raffle_info(update, context)
        

app.add_handler(CallbackQueryHandler(button_handler))

# ---------------- RUN THE BOT ---------------- #
if __name__ == "__main__":
    app.run_polling()
