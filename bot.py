import asyncio
import logging
import json
import os
import random
from aiohttp import web
from aiogram import Bot, Dispatcher
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
    """Load file_id cache from JSON file and normalize paths"""
    if os.path.exists(FILE_ID_CACHE_PATH):
        with open(FILE_ID_CACHE_PATH, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        
        # Normalize paths: convert all to forward slashes for cross-platform compatibility
        normalized_cache = {}
        for path, file_id in cache.items():
            normalized_path = path.replace('\\', '/')
            normalized_cache[normalized_path] = file_id
        
        return normalized_cache
    return {}


def save_file_id_cache(cache):
    """Save file_id cache to JSON file with normalized paths"""
    # Normalize paths before saving
    normalized_cache = {}
    for path, file_id in cache.items():
        normalized_path = path.replace('\\', '/')
        normalized_cache[normalized_path] = file_id
    
    with open(FILE_ID_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(normalized_cache, f, ensure_ascii=False, indent=2)


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
        "/protoss - Browse Protoss sounds\n"
        "/terran - Browse Terran sounds\n"
        "/zerg - Browse Zerg sounds\n"
        "/music - Browse music tracks\n"
        "/upload - Upload all audio files to Telegram\n"
        "/stats - Show statistics".format(bot_username, bot_username)
    )


@dp.message(Command("protoss"))
async def cmd_protoss(message: Message):
    await send_category_sounds(message, "protoss", "⚡ Protoss Sounds")


@dp.message(Command("terran"))
async def cmd_terran(message: Message):
    await send_category_sounds(message, "terran", "🔧 Terran Sounds")


@dp.message(Command("zerg"))
async def cmd_zerg(message: Message):
    await send_category_sounds(message, "zerg", "👾 Zerg Sounds")


@dp.message(Command("music"))
async def cmd_music(message: Message):
    await send_category_sounds(message, "music", "🎵 Music Tracks")


async def send_category_sounds(message: Message, category: str, title: str):
    """Send sample sounds from a specific category"""
    # Get all files from category
    category_files = [
        (path, name) for path, name in audio_manager.get_all_files().items()
        if path.startswith(category + '/')
    ]
    
    if not category_files:
        await message.answer(f"No sounds found in {category} category.")
        return
    
    # Show 10 random files
    sample_size = min(10, len(category_files))
    samples = random.sample(category_files, sample_size)
    
    response = f"{title}\n\n"
    response += f"Showing {sample_size} random sounds of {len(category_files)} total:\n\n"
    
    for path, name in samples:
        # Send actual voice message if cached
        if path in file_id_cache:
            try:
                await message.answer_voice(
                    voice=file_id_cache[path],
                    caption=name
                )
                await asyncio.sleep(0.3)  # Small delay between messages
            except Exception as e:
                logger.error(f"Error sending voice {path}: {e}")
        else:
            response += f"• {name}\n"
    
    if sample_size < len(category_files):
        bot_username = (await bot.get_me()).username
        response += "\n💡 Use inline mode to search all sounds:\n"
        response += f"@{bot_username} {category}\n\n"
        response += f"🔄 Send /{category} again for different random samples!"
    
    await message.answer(response)


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
                
                # Increased delay to avoid rate limits (1 second between uploads)
                await asyncio.sleep(1.0)
                
                # Save cache periodically
                if uploaded % 10 == 0:
                    save_file_id_cache(file_id_cache)
                    progress_msg = (
                        f"✅ Progress: {uploaded + skipped}/{total_files}\n"
                        f"Uploaded: {uploaded} | Skipped: {skipped} | Errors: {errors}"
                    )
                    try:
                        await message.answer(progress_msg)
                    except TelegramRetryAfter:
                        # If we can't send progress, just continue
                        logger.warning("Can't send progress message due to rate limit")
                
                break  # Success, exit retry loop
                
            except TelegramRetryAfter as e:
                # Rate limit hit, wait and retry
                retry_after = e.retry_after
                logger.warning(f"Rate limit hit. Waiting {retry_after} seconds...")
                
                # Try to notify user, but don't fail if this also hits rate limit
                try:
                    await message.answer(
                        f"⏸️ Rate limit reached. Pausing for {retry_after} seconds..."
                    )
                except TelegramRetryAfter:
                    # Can't send message, just log it
                    logger.warning("Can't send pause notification due to rate limit")
                
                # Wait the required time plus buffer
                await asyncio.sleep(retry_after + 2)
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
    
    try:
        await message.answer(
            f"✅ Upload completed!\n"
            f"Total: {total_files}\n"
            f"Uploaded: {uploaded}\n"
            f"Skipped: {skipped}\n"
            f"Errors: {errors}"
        )
    except TelegramRetryAfter as e:
        # If final message fails, just log completion
        logger.info(f"Upload completed: {uploaded} uploaded, {skipped} skipped, {errors} errors")
        await asyncio.sleep(e.retry_after)
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
    
    logger.info(f"Inline query received: '{query}' from user {inline_query.from_user.id}")
    
    # Search for matching audio files
    results = audio_manager.search(query, limit=50)
    
    logger.info(f"Found {len(results)} search results")
    
    if not results:
        # Show "no results" message
        logger.warning(f"No results found for query: '{query}'")
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
            logger.warning(f"File not in cache: {relative_path}")
            continue
        
        result = InlineQueryResultCachedVoice(
            id=str(idx),
            voice_file_id=file_id_cache[relative_path],
            title=display_name
        )
        
        inline_results.append(result)
    
    logger.info(f"Sending {len(inline_results)} inline results")
    
    if not inline_results:
        logger.warning("No cached files found for results")
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
    
    # Create simple web server for health checks (keeps Render alive)
    app = web.Application()
    
    async def health_check(request):
        return web.Response(text="Bot is running! Audio files: {}, Cached: {}".format(
            len(audio_manager.audio_files), 
            len(file_id_cache)
        ))
    
    async def debug_files(request):
        # Show first 10 files for debugging
        files_list = list(audio_manager.audio_files.items())[:10]
        debug_info = "First 10 files:\n"
        for path, name in files_list:
            full_path = audio_manager.get_file_path(path)
            exists = os.path.exists(full_path)
            size = os.path.getsize(full_path) if exists else 0
            debug_info += f"\n{name}\n  Path: {path}\n  Exists: {exists}\n  Size: {size} bytes\n"
        return web.Response(text=debug_info)
    
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    app.router.add_get("/debug", debug_files)
    
    # Get port from environment (Render sets this)
    port = int(os.getenv('PORT', 10000))
    
    # Start web server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Health check server started on port {port}")
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.session.close()
        await runner.cleanup()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Bot stopped gracefully")
