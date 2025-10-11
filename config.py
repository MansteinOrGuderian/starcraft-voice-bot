import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
AUDIO_DIR = 'audio_files'
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))
