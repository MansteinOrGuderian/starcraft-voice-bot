import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    InlineQuery, InlineQueryResultCachedVoice,
    Message, FSInputFile
)
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter
from config import BOT_TOKEN, AUDIO_DIR
from audio_manager import AudioManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
audio_manager = AudioManager(AUDIO_DIR)

# File to store file_ids persistently
FILE_ID_CACHE_PATH = 'file_id_cache.json'


def load_file_id_cache():
    """Load file_id cache from JSON file"""
    if os.path.exists(FILE_ID_CACHE_PATH):
        with open(FILE_ID_CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_file_id_cache(cache):
    """Save file_id cache to JSON file"""
    with open(FILE_ID_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


file_id_cache = load_file_id_cache()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    bot_username = (await bot.get_me()).username
    await message.answer(
        "👋 Hello! I'm a voice message bot.\n\n"
        "To use me:\n"
        "1. Type @{} in any chat\n"
        "2. Enter part of the audio name\n"
        "3. Choose the audio from the list\n\n"
        "Example: @{} zealot\n\n"
        "Commands:\n"
        "/upload - Upload all audio files to Telegram\n"
        "/stats - Show statistics".format(bot_username, bot_username)
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    total_files = len(audio_manager.audio_files)
    cached_files = len(file_id_cache)
    
    # Get stats by category
    category_stats = audio_manager.get_stats_by_category()
    
    stats_text = "📊 Statistics:\n\n"
    stats_text += f"Total audio files: {total_files}\n"
    stats_text += f"Uploaded to Telegram: {cached_files}\n\n"
    stats_text += "By category:\n"
    
    for category, count in sorted(category_stats.items()):
        cached_in_cat = sum(1 for path in file_id_cache.keys() if path.startswith(category))
        stats_text += f"  • {category.title()}: {count} (uploaded: {cached_in_cat})\n"
    
    await message.answer(stats_text)


@dp.message(Command("upload"))
async def cmd_upload(message: Message):
    """Upload all audio files to Telegram and cache their file_ids"""
    await message.answer("⏳ Starting audio file upload...")
    
    uploaded = 0
    skipped = 0
    errors = 0
    
    all_files = audio_manager.get_all_files()
    total_files = len(all_files)
    
    for relative_path, display_name in all_files.items():
        if relative_path in file_id_cache:
            skipped += 1
            continue
        
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                file_path = audio_manager.get_file_path(relative_path)
                voice = FSInputFile(file_path)
                
                # Send voice message to this chat
                sent_message = await message.answer_voice(voice)
                
                # Cache the file_id with relative path as key
                file_id_cache[relative_path] = sent_message.voice.file_id
                uploaded += 1
                
                # Delete the message to keep chat clean
                await sent_message.delete()
                
                # Add delay to avoid rate limits (0.5 seconds between uploads)
                await asyncio.sleep(0.5)
                
                # Save cache periodically
                if uploaded % 10 == 0:
                    save_file_id_cache(file_id_cache)
                    progress_msg = (
                        f"✅ Progress: {uploaded + skipped}/{total_files}\n"
                        f"Uploaded: {uploaded} | Skipped: {skipped} | Errors: {errors}"
                    )
                    await message.answer(progress_msg)
                
                break  # Success, exit retry loop
                
            except TelegramRetryAfter as e:
                # Rate limit hit, wait and retry
                retry_after = e.retry_after
                logger.warning(f"Rate limit hit. Waiting {retry_after} seconds...")
                await message.answer(
                    f"⏸️ Rate limit reached. Pausing for {retry_after} seconds..."
                )
                await asyncio.sleep(retry_after + 1)
                retry_count += 1
                
            except Exception as e:
                logger.error(f"Error uploading {relative_path}: {e}")
                errors += 1
                retry_count += 1
                await asyncio.sleep(1)
        
        if retry_count >= max_retries:
            logger.error(f"Failed to upload {relative_path} after {max_retries} retries")
    
    # Save final cache
    save_file_id_cache(file_id_cache)
    
    await message.answer(
        f"✅ Upload completed!\n"
        f"Total: {total_files}\n"
        f"Uploaded: {uploaded}\n"
        f"Skipped: {skipped}\n"
        f"Errors: {errors}"
    )


@dp.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    query = inline_query.query.strip()
    
    # Search for matching audio files
    results = audio_manager.search(query, limit=50)
    
    if not results:
        # Show "no results" message
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True
        )
        return
    
    # Prepare inline results
    inline_results = []
    
    for idx, (relative_path, display_name, _) in enumerate(results):
        # Only show files that have been uploaded to Telegram
        if relative_path not in file_id_cache:
            continue
        
        result = InlineQueryResultCachedVoice(
            id=str(idx),
            voice_file_id=file_id_cache[relative_path],
            title=display_name
        )
        
        inline_results.append(result)
    
    if not inline_results:
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True
        )
        return
    
    await inline_query.answer(
        results=inline_results[:50],  # Telegram limits to 50 results
        cache_time=300,
        is_personal=True
    )


async def main():
    logger.info("Starting bot...")
    
    # Load audio files
    audio_manager._load_audio_files()
    logger.info(f"Loaded {len(audio_manager.audio_files)} audio files")
    logger.info(f"Cached {len(file_id_cache)} file IDs")
    
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
