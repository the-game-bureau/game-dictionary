#!/usr/bin/env python3
"""
Game Dictionary Downloader with Integrated Logging
Downloads lightweight dictionaries perfect for word games
Logs all activities to /logs/log.txt for viewing in log_reader.html
"""

import os
import sys
import requests
import json
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime
import threading

# Game Dictionary Sources - Reordered with Simple English Dictionary first
GAME_DICTIONARIES = {
    "simple_english": {
        "name": "🌟 Simple English Dictionary (RECOMMENDED for Games)",
        "url": "https://raw.githubusercontent.com/nightblade9/simple-english-dictionary/master/processed/combined.json",
        "filename": "simple_english_dictionary.json",
        "description": "✅ 40k words with clean definitions - perfect for games!",
        "size": "~5MB",
        "has_definitions": True,
        "has_parts_of_speech": "Limited"
    },
    "simple_english_filtered": {
        "name": "👨‍👩‍👧‍👦 Simple English Dictionary (Kid-Safe)",
        "url": "https://raw.githubusercontent.com/nightblade9/simple-english-dictionary/master/processed/filtered.json",
        "filename": "simple_english_filtered.json",
        "description": "✅ Family-friendly version with definitions (filtered content)",
        "size": "~4MB",
        "has_definitions": True,
        "has_parts_of_speech": "Limited"
    },
    "websters_complete": {
        "name": "📚 Webster's Dictionary (Complete w/ Definitions & Parts of Speech)",
        "url": "https://github.com/ssvivian/WebstersDictionary/raw/master/dictionary.json",
        "filename": "websters_complete.json",
        "description": "✅ 75k words with definitions, parts of speech, and synonyms - comprehensive",
        "size": "~15MB",
        "has_definitions": True,
        "has_parts_of_speech": True
    },
    "english_words": {
        "name": "📝 English Words Collection (479k words)",
        "url": "https://raw.githubusercontent.com/dwyl/english-words/master/words_dictionary.json",
        "filename": "english_words_479k.json",
        "description": "❌ Word validation only - no definitions or parts of speech",
        "size": "~6MB",
        "has_definitions": False,
        "has_parts_of_speech": False
    },
    "english_words_alpha": {
        "name": "🔤 English Words (Alpha Only)",
        "url": "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt",
        "filename": "english_words_alpha.txt",
        "description": "❌ Word list only - no definitions or parts of speech",
        "size": "~4MB",
        "has_definitions": False,
        "has_parts_of_speech": False
    },
    "scrabble_dictionary": {
        "name": "🎯 Scrabble Dictionary JSON",
        "url": "https://raw.githubusercontent.com/benjamincrom/scrabble/master/scrabble/dictionary.json",
        "filename": "scrabble_dictionary.json",
        "description": "❌ Game words only - no definitions or parts of speech",
        "size": "~2MB",
        "has_definitions": False,
        "has_parts_of_speech": False
    }
}

class LogWriter:
    """Thread-safe log writer compatible with log_reader.html"""
    
    def __init__(self, repo_root):
        """Initialize the log writer"""
        logs_dir = repo_root / "logs"
        logs_dir.mkdir(exist_ok=True)
        self.log_file = logs_dir / "log.txt"
        self._lock = threading.Lock()
        
    def _get_timestamp(self):
        """Get ISO formatted timestamp that the web reader expects"""
        return datetime.now().isoformat()
    
    def _write_entry(self, level, message, display_level=None):
        """Write a log entry to the file"""
        timestamp = self._get_timestamp()
        
        if display_level and display_level != level:
            log_line = f"{level.upper()}|{timestamp}|{display_level.upper()}|{message}"
        else:
            log_line = f"{level.upper()}|{timestamp}|{message}"
        
        with self._lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_line + '\n')
                f.flush()
    
    def info(self, message):
        """Write an INFO level log entry (blue styling)"""
        self._write_entry('info', message)
        
    def start(self, message):
        """Write a START level log entry (orange styling)"""
        self._write_entry('start', message)
        
    def progress(self, message, percentage=None, bytes_info=None):
        """Write a PROGRESS level log entry (purple styling)"""
        full_message = message
        if percentage is not None:
            full_message += f" - {percentage}%"
        if bytes_info:
            full_message += f" ({bytes_info:,} bytes)"
        self._write_entry('progress', full_message)
        
    def complete(self, message):
        """Write a COMPLETE level log entry (green styling)"""
        self._write_entry('complete', message)
        
    def error(self, message):
        """Write an ERROR level log entry (red styling)"""
        self._write_entry('error', message)
        
    def warning(self, message):
        """Write a WARNING level log entry (orange-red styling)"""
        self._write_entry('warning', message)

def find_repo_root():
    """Find the git repository root directory"""
    current_dir = Path(__file__).parent.absolute()
    
    # Walk up the directory tree looking for .git folder
    while current_dir != current_dir.parent:
        if (current_dir / '.git').exists():
            return current_dir
        current_dir = current_dir.parent
    
    # If no .git found, fall back to script directory
    return Path(__file__).parent

def create_data_folder():
    """Create data folder in repository root if it doesn't exist"""
    repo_root = find_repo_root()
    data_folder = repo_root / "data"
    data_folder.mkdir(exist_ok=True)
    return data_folder

def setup_logging():
    """Setup logging to /logs/log.txt"""
    repo_root = find_repo_root()
    return LogWriter(repo_root)

def download_file(url, filepath, chunk_size=8192, logger=None):
    """Download a file with progress indication and logging"""
    if logger:
        logger.info(f"Starting download: {filepath.name}")
        logger.progress(f"Downloading {filepath.name}", percentage=0)
    
    print(f"  📥 Downloading from: {url}")
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r     Progress: {percent:.1f}% ({downloaded:,}/{total_size:,} bytes)", end='')
                        
                        # Log progress at 25% intervals
                        if logger and percent >= 0 and int(percent) % 25 == 0 and int(percent) > 0:
                            if not hasattr(download_file, f'logged_{int(percent)}_{filepath.name}'):
                                logger.progress(f"Downloading {filepath.name}", percentage=int(percent), bytes_info=downloaded)
                                setattr(download_file, f'logged_{int(percent)}_{filepath.name}', True)
                    else:
                        print(f"\r     Downloaded: {downloaded:,} bytes", end='')
        
        print(f"\n  ✅ Downloaded: {filepath.name}")
        if logger:
            logger.complete(f"Successfully downloaded {filepath.name} ({downloaded:,} bytes)")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n  ❌ Download failed: {e}")
        if logger:
            logger.error(f"Failed to download {filepath.name}: {str(e)}")
        return False

def verify_file(filepath, dict_key, logger=None):
    """Verify downloaded file and show basic info"""
    try:
        file_size = filepath.stat().st_size
        dict_info = GAME_DICTIONARIES[dict_key]
        
        print(f"     💾 File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
        
        if logger:
            logger.info(f"Verifying {filepath.name} ({file_size:,} bytes)")
        
        if filepath.suffix == '.json':
            # Verify JSON format and show sample
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check format for Webster's complete dictionary
            if dict_key == "websters_complete" and isinstance(data, list) and len(data) > 0:
                sample_entry = data[0]
                word_count = len(data)
                print(f"     📊 {word_count:,} dictionary entries found")
                
                if logger:
                    logger.info(f"Webster's dictionary loaded: {word_count:,} entries")
                
                if isinstance(sample_entry, dict):
                    print(f"     📝 Sample word: '{sample_entry.get('word', 'N/A')}'")
                    print(f"     🏷️  Part of speech: {sample_entry.get('pos', 'N/A')}")
                    definitions = sample_entry.get('definitions', [])
                    if definitions:
                        print(f"     📖 Definition: {definitions[0][:60]}...")
                    else:
                        print(f"     📖 Definition: N/A")
                    
            elif isinstance(data, dict):
                word_count = len(data)
                sample_words = list(data.items())[:3]
                print(f"     📊 {word_count:,} words found")
                
                if logger:
                    logger.info(f"Dictionary loaded: {word_count:,} words")
                
                # Show format info
                first_key, first_value = sample_words[0]
                if isinstance(first_value, dict):
                    print(f"     📝 Sample: {first_key}")
                    if 'definition' in first_value:
                        print(f"     📖 Has definitions: ✅")
                    if 'pos' in first_value or 'part_of_speech' in first_value:
                        print(f"     🏷️  Has parts of speech: ✅")
                else:
                    print(f"     📝 Sample: {', '.join([k for k, v in sample_words])}")
                    
            elif isinstance(data, list):
                word_count = len(data)
                sample_words = data[:3]
                print(f"     📊 {word_count:,} entries found")
                print(f"     📝 Sample: {', '.join(str(w) for w in sample_words)}")
                
                if logger:
                    logger.info(f"List data loaded: {word_count:,} entries")
                
        elif filepath.suffix == '.txt':
            # Count lines for text files
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                word_count = len([line.strip() for line in lines if line.strip()])
                sample_words = [line.strip() for line in lines[:3] if line.strip()]
                
            print(f"     📊 {word_count:,} words found")
            print(f"     📝 Sample: {', '.join(sample_words)}")
            
            if logger:
                logger.info(f"Text file loaded: {word_count:,} words")
        
        # Show what features this dictionary has
        if dict_info.get('has_definitions'):
            print(f"     ✅ Includes definitions")
        if dict_info.get('has_parts_of_speech'):
            print(f"     ✅ Includes parts of speech")
        
        if logger:
            logger.complete(f"Successfully verified {filepath.name}")
            
        return True
        
    except Exception as e:
        print(f"     ⚠️  Error verifying file: {e}")
        if logger:
            logger.error(f"Failed to verify {filepath.name}: {str(e)}")
        return False

def show_dictionary_menu():
    """Show available dictionaries and let user choose"""
    print("\n🎮 Available Game Dictionaries:")
    print("=" * 70)
    print("📋 LEGEND: ✅ = Has definitions & parts of speech | ❌ = Word lists only")
    print()
    
    for i, (key, info) in enumerate(GAME_DICTIONARIES.items(), 1):
        print(f"{i:2d}. {info['name']}")
        print(f"     📖 {info['description']}")
        print(f"     📏 Size: {info['size']}")
        
        # Show what's included
        features = []
        if info.get('has_definitions'):
            features.append("✅ Definitions")
        if info.get('has_parts_of_speech') == True:
            features.append("✅ Parts of Speech")
        elif info.get('has_parts_of_speech') == "Limited":
            features.append("⚠️ Some Parts of Speech")
        
        if features:
            print(f"     🎯 Features: {' | '.join(features)}")
        else:
            print(f"     🎯 Features: ❌ Word validation only")
        print()
    
    print("0. Download ALL dictionaries")
    print("r. Show RECOMMENDED dictionary only")
    print("q. Quit")
    return input("\nChoose dictionary to download (number/0/r/q): ").strip().lower()

def download_dictionary(dict_key, dict_info, data_folder, logger=None):
    """Download a specific dictionary"""
    print(f"\n🔄 Downloading: {dict_info['name']}")
    print(f"📄 {dict_info['description']}")
    
    if logger:
        logger.start(f"Starting download: {dict_info['name']}")
    
    filepath = data_folder / dict_info['filename']
    
    # Check if file exists
    if filepath.exists():
        file_size = filepath.stat().st_size
        print(f"  ⚠️  File exists ({file_size:,} bytes)")
        if logger:
            logger.warning(f"File already exists: {dict_info['filename']} ({file_size:,} bytes)")
        
        response = input(f"  Replace existing file? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("  ⏭️  Skipped")
            if logger:
                logger.info(f"Skipped download: {dict_info['filename']} (user choice)")
            return True
    
    # Download file
    if download_file(dict_info['url'], filepath, logger=logger):
        return verify_file(filepath, dict_key, logger=logger)
    return False

def convert_txt_to_json(data_folder, logger=None):
    """Convert text files to JSON for easier use"""
    print("\n🔄 Converting text files to JSON...")
    
    if logger:
        logger.info("Starting text to JSON conversion")
    
    txt_files = {
        "english_words_alpha.txt": "english_words_alpha.json",
        "sowpods_scrabble.txt": "sowpods_scrabble.json"
    }
    
    for txt_name, json_name in txt_files.items():
        txt_path = data_folder / txt_name
        json_path = data_folder / json_name
        
        if txt_path.exists() and not json_path.exists():
            try:
                if logger:
                    logger.progress(f"Converting {txt_name} to JSON", percentage=0)
                    
                with open(txt_path, 'r', encoding='utf-8') as f:
                    words = [line.strip().lower() for line in f if line.strip()]
                
                # Create dictionary format for games
                word_dict = {word: 1 for word in words}
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(word_dict, f, separators=(',', ':'))
                
                print(f"  ✅ Converted: {json_name} ({len(words):,} words)")
                if logger:
                    logger.complete(f"Converted {txt_name} to {json_name} ({len(words):,} words)")
                
            except Exception as e:
                print(f"  ❌ Failed to convert {txt_name}: {e}")
                if logger:
                    logger.error(f"Failed to convert {txt_name}: {str(e)}")

def show_summary(data_folder, logger=None):
    """Show summary of downloaded files"""
    print("\n📋 Downloaded Dictionaries Summary:")
    print("=" * 50)
    
    if logger:
        logger.info("Generating download summary")
    
    json_files = list(data_folder.glob("*.json"))
    txt_files = list(data_folder.glob("*.txt"))
    
    total_size = 0
    total_files = len(json_files + txt_files)
    
    for file_path in sorted(json_files + txt_files):
        size = file_path.stat().st_size
        total_size += size
        
        # Count words for JSON files
        word_count = "?"
        if file_path.suffix == '.json':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        word_count = f"{len(data):,}"
                    elif isinstance(data, list):
                        word_count = f"{len(data):,}"
            except:
                pass
        elif file_path.suffix == '.txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    word_count = f"{len([l for l in lines if l.strip()]):,}"
            except:
                pass
        
        print(f"📁 {file_path.name}")
        print(f"   💾 {size:,} bytes ({size/1024/1024:.1f} MB)")
        print(f"   📊 {word_count} words")
        print()
    
    print(f"🎯 Total: {total_files} files, {total_size/1024/1024:.1f} MB")
    print(f"📂 Location: {data_folder.absolute()}")
    
    if logger:
        logger.complete(f"Download session completed: {total_files} files, {total_size/1024/1024:.1f} MB total")
        logger.info(f"Dictionary files location: {data_folder.absolute()}")

def main():
    """Main function"""
    print("🎮 Game Dictionary Downloader")
    print("=" * 40)
    print("Lightweight dictionaries perfect for word games!")
    
    # Setup logging
    logger = setup_logging()
    logger.start("Game Dictionary Downloader started")
    
    # Create data folder at repository root
    data_folder = create_data_folder()
    repo_root = find_repo_root()
    
    print(f"📂 Repository root: {repo_root.absolute()}")
    print(f"📂 Data folder: {data_folder.absolute()}")
    print(f"📝 Log file: {logger.log_file.absolute()}")
    
    logger.info(f"Data folder: {data_folder.absolute()}")
    logger.info(f"Log file: {logger.log_file.absolute()}")
    
    # Check existing files
    existing_files = list(data_folder.glob("*.json")) + list(data_folder.glob("*.txt"))
    if existing_files:
        print(f"\n📁 Found {len(existing_files)} existing files")
        logger.info(f"Found {len(existing_files)} existing dictionary files")
    
    while True:
        choice = show_dictionary_menu()
        
        if choice == 'q':
            print("👋 Goodbye!")
            logger.complete("Game Dictionary Downloader session ended")
            break
        elif choice == 'r':
            print("\n🌟 RECOMMENDED: Simple English Dictionary (Game-Friendly)")
            print("=" * 60)
            key = "simple_english"
            info = GAME_DICTIONARIES[key]
            print(f"📖 {info['name']}")
            print(f"📖 {info['description']}")
            print("🎯 Why recommended for games:")
            print("   ✅ Clean, simple definitions (not overly complex)")
            print("   ✅ Game-optimized word selection")
            print("   ✅ Smaller file size (~5MB vs 15MB)")
            print("   ✅ Kid-friendly content available")
            print("   ✅ Perfect balance of features vs performance")
            print("   ✅ JSON format - easy to parse")
            print("   ⚠️  Limited parts of speech (not every word)")
            print()
            
            logger.info("User selected recommended dictionary: Simple English Dictionary")
            
            confirm = input("Download Simple English Dictionary? (Y/n): ").strip().lower()
            if confirm in ['', 'y', 'yes']:
                if download_dictionary(key, info, data_folder, logger):
                    convert_txt_to_json(data_folder, logger)
                    show_summary(data_folder, logger)
                break
            else:
                logger.info("Download cancelled by user")
            
        elif choice == '0':
            print("\n🚀 Downloading ALL dictionaries...")
            logger.start("Starting bulk download of all dictionaries")
            success_count = 0
            for key, info in GAME_DICTIONARIES.items():
                if download_dictionary(key, info, data_folder, logger):
                    success_count += 1
            
            print(f"\n✅ Downloaded {success_count}/{len(GAME_DICTIONARIES)} dictionaries")
            logger.complete(f"Bulk download completed: {success_count}/{len(GAME_DICTIONARIES)} dictionaries")
            convert_txt_to_json(data_folder, logger)
            show_summary(data_folder, logger)
            break
        else:
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(GAME_DICTIONARIES):
                    key = list(GAME_DICTIONARIES.keys())[choice_num - 1]
                    info = GAME_DICTIONARIES[key]
                    
                    logger.info(f"User selected dictionary: {info['name']}")
                    
                    if download_dictionary(key, info, data_folder, logger):
                        convert_txt_to_json(data_folder, logger)
                        show_summary(data_folder, logger)
                    
                    another = input("\nDownload another? (y/N): ").strip().lower()
                    if another not in ['y', 'yes']:
                        break
                else:
                    print("❌ Invalid choice. Please try again.")
                    logger.warning(f"Invalid menu choice: {choice}")
            except ValueError:
                print("❌ Invalid choice. Please enter a number.")
                logger.warning(f"Invalid input: {choice}")
    
    print()
    print("🌐 View logs: Open log_reader.html in your browser")
    log_path = str(logger.log_file.absolute())
    print(f"📝 Log location: {log_path}")

if __name__ == "__main__":
    main()