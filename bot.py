import logging
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import threading
from collections import defaultdict
import time
from dotenv import dotenv_values

# Enable logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
config = dotenv_values(".env")  # Load environment variables from .env file

# MongoDB connection
uri = config.get("YOUR_DB_URL") # Replace with your MongoDB URI

if not uri:
    print(uri)
    logger.error("Bot token not found. Please check your .env file.")
    exit()

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'), connectTimeoutMS=30000, socketTimeoutMS=30000)
# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
    # Access the database and collection
    db = client['vb_db']
    # shower_collection = db['shower']
    faq_collection = db['faq']
    users_collection = db['users']
    print("Connected to the database and collection successfully!")
except Exception as e:
    print(e)
    print("An error occurred while connecting to MongoDB. Check your URI or internet connection.")
    exit()

FAQ_type = ["Registration", "Programmes", "Revival Nights", "Premises", "Others"]
# Dictionary to store unanswered questions
unanswered_questions = {}

# Function to update admin and shower IDs from the database
def update_ids():
    global ADMIN_IDS 
    print("Updating IDs...")
    ADMIN_IDS = [user["id"] for user in users_collection.find() if user["type"] == "admin"]

    # SHOWER_IDS = [user["id"] for user in users_collection.find() if user["type"] == "shower"]
    print(f"Admin IDs: {ADMIN_IDS}")

    # Schedule the next update in 60 seconds
    threading.Timer(60, update_ids).start()

# Dictionary to store user message timestamps
user_message_timestamps = defaultdict(list)

# Function to handle messages
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.chat_id
    current_time = time.time()

    # Add current timestamp to the user's message timestamps
    user_message_timestamps[user_id].append(current_time)

    # Remove timestamps older than 10 seconds
    user_message_timestamps[user_id] = [timestamp for timestamp in user_message_timestamps[user_id] if current_time - timestamp <= 30]

    # Check if the user has sent more than 10 messages in the last 10 seconds
    if len(user_message_timestamps[user_id]) > 10:
        await update.message.reply_text("You are sending messages too quickly. Please wait a minute before sending more messages.")
        context.bot_data[user_id] = current_time + 60  # Timeout the user for 60 seconds
        global timeout_warning
        timeout_warning = True
        return

    # Check if the user is currently timed out
    if user_id in context.bot_data and current_time < context.bot_data[user_id]:
        if timeout_warning == False:
            return
        await update.message.reply_text("You are currently timed out. Your responeses will be ignored, please wait for a minute.")
        timeout_warning = False
        return

    if context.user_data.get('awaiting_number'):
        await update.message.reply_text("Please enter the number of people before asking another question.")
        return  

    user_message = update.message.text.lower()

    # Check local time (UTC +8)
    tz = pytz.timezone('Asia/Singapore')
    current_time = datetime.now(tz)
    if 23 <= current_time.hour or current_time.hour < 6:
        await update.message.reply_text("Please note that responses may be slower between 11 PM and 6 AM.")

    # Check if the message matches an FAQ

    # If question is not in FAQs, store it and notify the admins
    user = await context.bot.get_chat(user_id)
    username = user.first_name if user.first_name else user.username
    unanswered_questions[user_id] = user_message
    for admin_id in ADMIN_IDS:
        await context.bot.send_message(chat_id=admin_id, text=f"User {user_id} ({username}) asked: {user_message}")
    await update.message.reply_text("I don't have an answer right now. The admin will reply soon!")

# Function to handle number of people input
# async def handle_number_of_people(update: Update, context: CallbackContext) -> None:
#     if not context.user_data.get('awaiting_number'):
#         await handle_message(update, context)  # Pass control to handle_message if not expecting a number
#         return

#     try:
#         number_of_people = int(update.message.text)
#     except ValueError:
#         await update.message.reply_text("The number of people must be an integer.")
#         return

#     room_id = context.user_data['room_id']
#     room_names = {
#         '1': "Male Shower KB Side",
#         '2': "Male Shower Drum Side",
#         '3': "Female Shower KB Side",
#         '4': "Female Shower Drum Side"
#     }
#     room_name = room_names.get(room_id)

#     tz = pytz.timezone('Asia/Singapore')
#     current_time = datetime.now(tz)
#     formatted_time = current_time.strftime("%d/%m/%Y %H:%M")

#     shower_collection.insert_one({
#         "room_id": room_name,
#         "number_of_people": number_of_people,
#         "timestamp": formatted_time,
#         "ref_time": current_time
#     })

#     await update.message.reply_text(f"Shower record added successfully for {room_name} with {number_of_people} people at {formatted_time}.")
#     context.user_data.clear()
    
#     # Function to handle adding a shower entry
# async def add_shower(update: Update, context: CallbackContext) -> None:
#     if update.message.chat_id not in SHOWER_IDS:
#         await update.message.reply_text("You are not authorized to use this command.")
#         return

#     context.user_data['awaiting_shower_selection'] = True  # Ensure shower selection is required first

#     keyboard = [
#         [InlineKeyboardButton("Male Shower KB Side", callback_data='1')],
#         [InlineKeyboardButton("Male Shower Drum Side", callback_data='2')],
#         [InlineKeyboardButton("Female Shower KB Side", callback_data='3')],
#         [InlineKeyboardButton("Female Shower Drum Side", callback_data='4')]
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     await update.message.reply_text("Select the shower room:", reply_markup=reply_markup)

# # Handle button selection from inline keyboard
# async def button(update: Update, context: CallbackContext) -> None:
#     query = update.callback_query
#     await query.answer()
#     room_id = query.data

#     context.user_data.pop('awaiting_shower_selection', None)  # Remove selection flag
#     context.user_data['room_id'] = room_id
#     context.user_data['awaiting_number'] = True  # Expecting number input
#     await query.edit_message_text(text=f"Selected option: {room_id}. Now, please enter the number of people:")

# Function to handle FAQ command
async def faq(update: Update, context: CallbackContext) -> None:
    faq_text = "Here are some *Frequently Asked Questions* for the camp:\n"
    for faq_type in FAQ_type:
        faq_text += f"\n\n*{faq_type}*\n"
        faqs = faq_collection.find({"type": faq_type}).sort("title", 1)
        for faq in faqs:
            faq_text += f"• {faq['title']} - {faq['message']}\n"
    faq_text += "\n\nIf you have any other questions, feel free to ask the bot! We'll get back to you as soon as possible."

    await update.message.reply_text(faq_text, parse_mode='Markdown')

# Function to allow admin to reply
async def reply(update: Update, context: CallbackContext) -> None:
    if update.message.chat_id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <message>")
        return

    user_id = int(args[0])  # Extract user ID
    response_message = " ".join(args[1:])  # Extract response

    if user_id in unanswered_questions:
        await context.bot.send_message(chat_id=user_id, text=f"Admin says: {response_message}")
        del unanswered_questions[user_id]  # Remove question after response
        await update.message.reply_text("Reply sent successfully!")
    else:
        await update.message.reply_text("No pending question from this user.")

# Function to show latest shower records
# async def shower_status(update: Update, context: CallbackContext) -> None:
#     pipeline = [
#         {"$sort": {"ref_time": -1}},
#         {"$group": {"_id": "$room_id", "latest_record": {"$first": "$$ROOT"}}}
#     ]
#     results = list(shower_collection.aggregate(pipeline))

#     if results:
#         latest_timestamp = max(result["latest_record"]["timestamp"] for result in results)
#         response = f"Latest shower records:\n(Last updated: {latest_timestamp})\n"
#         for result in results:
#             room_id = result["latest_record"]["room_id"]
#             number_of_people = result["latest_record"]["number_of_people"]
#             response += f"\n{room_id}: {number_of_people} people on queue"
#         await update.message.reply_text(response)
#     else:
#         await update.message.reply_text("No shower records found.")
        
# # Function to show packing list
# async def packing_list(update: Update, context: CallbackContext) -> None:
#     packing_text = "Here is the packing list for the camp\n\n"
#     photo_url = "./packing.jpg"  # Replace with your actual image URL
#     await update.message.reply_photo(photo=photo_url, caption=packing_text, parse_mode='Markdown')
    
async def cmd_list (update: Update, context: CallbackContext) -> None:
    if update.message.chat_id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    await update.message.reply_text("Available commands for admins/shower IC:\n\n/reply - Reply to user\n/add_shower - Add shower entry")
    

# Function to add command handlers and start bot
def main():
    TOKEN = config.get("YOUR_BOT_TOKEN")  # Replace with your bot token
    
    if not TOKEN:
        print(TOKEN)
        logger.error("Bot token not found. Please check your .env file.")
        exit()

    app = Application.builder().token(TOKEN).build()
    
    # Initial update of IDs
    update_ids()

    # app.add_handler(CommandHandler("start", faq))
    # app.add_handler(CommandHandler("faq", faq))
    app.add_handler(CommandHandler("reply", reply))
    # app.add_handler(CommandHandler("shower", shower_status))
    # app.add_handler(CommandHandler("add_shower", add_shower))
    # app.add_handler(CommandHandler("packing", packing_list))
    app.add_handler(CommandHandler("command", cmd_list))
    app.add_handler(CommandHandler("cmd", cmd_list))
    # app.add_handler(CallbackQueryHandler(button))
    # app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number_of_people))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()