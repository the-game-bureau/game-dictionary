#!/usr/bin/env python3
"""
Combined Dictionary Management Tools

This script provides three main functions:
1. Download and maintain the ENABLE word list (word_fetcher functionality)
2. Convert words.txt to dictionary.xml format (xml_converter functionality)  
3. Add real dictionary definitions and parts of speech to words in dictionary.xml

Usage:
  python dictionary_tools.py [command]
  
Commands:
  fetch     - Download/update word list from ENABLE
  convert   - Convert words.txt to dictionary.xml
  define    - Add real dictionary definitions to 100 words in dictionary.xml
  all       - Run all commands in sequence (fetch -> convert -> define)
  
If no command is specified, shows interactive menu.

Requirements:
  - Python 3.x
  - Internet connection (for fetch command)

File Structure:
  - data/words.txt      # Plain text word list
  - data/dictionary.xml # XML formatted dictionary
  - logs/log.txt        # Appended log entries
"""

import sys
import urllib.request
from pathlib import Path
import logging
import shutil
import time
import urllib.error
import xml.etree.ElementTree as ET
from xml.dom import minidom
import random
import argparse
import json

# Configuration constants
DOWNLOAD_TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5
CHUNK_SIZE = 8192
ENABLE_URL = "https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt"

# Free Dictionary API (no API key required)
DICTIONARY_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"

# WordsAPI (freemium - 2500 requests/day with API key via RapidAPI)
WORDSAPI_URL = "https://wordsapiv1.p.rapidapi.com/words/"
# Set your API key here if you want to use WordsAPI (get free key at rapidapi.com)
RAPIDAPI_KEY = None  # Replace with your API key for 2500 extra requests/day

# Wordnik API (free tier available)
WORDNIK_API_URL = "https://api.wordnik.com/v4/word.json/"
WORDNIK_API_KEY = None  # Replace with your API key for even more requests

API_TIMEOUT = 10
API_RETRY_DELAY = 1

def find_project_root():
    """Find the project root by traversing up from the script location."""
    current = Path(__file__).resolve().parent
    
    while current.parent != current:
        root_indicators = [
            '.git', '.gitignore', 'requirements.txt', 'setup.py', 
            'pyproject.toml', 'README.md', 'README.txt', 'LICENSE',
            'package.json', 'Makefile', '.env'
        ]
        
        if any((current / indicator).exists() for indicator in root_indicators):
            return current
        
        current = current.parent
    
    return Path(__file__).resolve().parent

def setup_logging():
    """Set up logging configuration for all operations."""
    base_dir = find_project_root()
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / "log.txt"
    
    logging.getLogger().handlers.clear()
    
    logging.basicConfig(
        filename=str(log_path),
        filemode='a',
        level=logging.INFO,
        format='%(levelname)s|%(asctime)s|%(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    logger = logging.getLogger()
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console_fmt = logging.Formatter('%(levelname)s|%(asctime)s|%(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
    console.setFormatter(console_fmt)
    logger.addHandler(console)
    
    return logger

def get_file_paths():
    """Get standardized file paths for all operations."""
    base_dir = find_project_root()
    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    
    words_path = data_dir / "words.txt"
    xml_path = data_dir / "dictionary.xml"
    backup_path = data_dir / "words_backup.txt"
    
    return base_dir, data_dir, words_path, xml_path, backup_path

def lookup_definition_free_dict(word, logger=None):
    """Look up definition from Free Dictionary API (no key required)."""
    try:
        url = f"{DICTIONARY_API_URL}{word.lower()}"
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'DictionaryTools/1.0')
        
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if not data or not isinstance(data, list):
            return None
        
        entry = data[0]
        if 'meanings' not in entry or not entry['meanings']:
            return None
        
        meaning = entry['meanings'][0]
        part_of_speech = meaning.get('partOfSpeech', 'unknown')
        
        if 'definitions' not in meaning or not meaning['definitions']:
            return None
        
        definition = meaning['definitions'][0].get('definition', '')
        
        if definition:
            definition = definition.strip()
            if definition.endswith('.'):
                definition = definition[:-1]
            if definition:
                definition = definition[0].upper() + definition[1:]
            return (definition, part_of_speech)
        
        return None
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        else:
            if logger:
                logger.warning(f"Free Dict API HTTP error for '{word}': {e.code}")
            return None
    except Exception as e:
        if logger:
            logger.warning(f"Free Dict API error for '{word}': {e}")
        return None

def lookup_definition_wordsapi(word, logger=None):
    """Look up definition from WordsAPI (requires RapidAPI key)."""
    if not RAPIDAPI_KEY:
        return None
        
    try:
        url = f"{WORDSAPI_URL}{word.lower()}"
        request = urllib.request.Request(url)
        request.add_header('X-RapidAPI-Key', RAPIDAPI_KEY)
        request.add_header('X-RapidAPI-Host', 'wordsapiv1.p.rapidapi.com')
        request.add_header('User-Agent', 'DictionaryTools/1.0')
        
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if 'results' not in data or not data['results']:
            return None
        
        result = data['results'][0]
        definition = result.get('definition', '')
        part_of_speech = result.get('partOfSpeech', 'unknown')
        
        if definition:
            definition = definition.strip()
            if definition.endswith('.'):
                definition = definition[:-1]
            if definition:
                definition = definition[0].upper() + definition[1:]
            return (definition, part_of_speech)
        
        return None
        
    except urllib.error.HTTPError as e:
        error_msg = f"WordsAPI HTTP {e.code}"
        
        # Read error response for more details
        try:
            error_response = e.read().decode('utf-8')
            error_data = json.loads(error_response)
            if 'message' in error_data:
                error_msg += f": {error_data['message']}"
        except:
            pass
            
        if e.code == 401:
            error_msg += " (Invalid API key - check your RapidAPI key)"
        elif e.code == 403:
            error_msg += " (Rate limit exceeded or subscription required)"
        elif e.code == 404:
            return None  # Word not found - this is normal
        elif e.code == 429:
            error_msg += " (Too many requests - rate limited)"
        
        if logger:
            logger.warning(f"{error_msg} for word '{word}'")
        else:
            print(f"   ⚠️  {error_msg}")
        return None
        
    except Exception as e:
        if logger:
            logger.warning(f"WordsAPI error for '{word}': {e}")
        else:
            print(f"   ⚠️  WordsAPI error for '{word}': {e}")
        return None

def lookup_definition_wordnik(word, logger=None):
    """Look up definition from Wordnik API (requires free API key)."""
    if not WORDNIK_API_KEY:
        return None
        
    try:
        url = f"{WORDNIK_API_URL}{word.lower()}/definitions?limit=1&includeRelated=false&sourceDictionaries=all&useCanonical=false&includeTags=false&api_key={WORDNIK_API_KEY}"
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'DictionaryTools/1.0')
        
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if not data or not isinstance(data, list):
            return None
        
        definition_obj = data[0]
        definition = definition_obj.get('text', '')
        part_of_speech = definition_obj.get('partOfSpeech', 'unknown')
        
        if definition:
            definition = definition.strip()
            if definition.endswith('.'):
                definition = definition[:-1]
            if definition:
                definition = definition[0].upper() + definition[1:]
            return (definition, part_of_speech)
        
        return None
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        else:
            if logger:
                logger.warning(f"Wordnik API HTTP error for '{word}': {e.code}")
            return None
    except Exception as e:
        if logger:
            logger.warning(f"Wordnik API error for '{word}': {e}")
        return None

def lookup_definition(word, logger=None):
    """
    Look up definition using multiple APIs as fallbacks.
    Returns tuple of (definition, part_of_speech) or None if not found.
    """
    # Try APIs in order of preference
    apis = [
        ("Free Dictionary", lookup_definition_free_dict),
        ("WordsAPI", lookup_definition_wordsapi),
        ("Wordnik", lookup_definition_wordnik),
    ]
    
    for api_name, api_func in apis:
        result = api_func(word, logger)
        if result:
            if logger:
                logger.debug(f"Found definition for '{word}' using {api_name}")
            return result
        
        # Small delay between API calls
        time.sleep(0.1)
    
    return None

def test_apis(logger=None):
    """Test all configured APIs with a simple word to verify they're working."""
    test_word = "hello"
    print(f"\n🧪 Testing APIs with word '{test_word}'...")
    
    # Test Free Dictionary API
    result = lookup_definition_free_dict(test_word, logger)
    if result:
        print(f"   ✅ Free Dictionary API: Working")
    else:
        print(f"   ❌ Free Dictionary API: Failed")
    
    # Test WordsAPI if key is provided
    if RAPIDAPI_KEY:
        result = lookup_definition_wordsapi(test_word, logger)
        if result:
            print(f"   ✅ WordsAPI: Working")
        else:
            print(f"   ❌ WordsAPI: Failed (check your API key)")
    else:
        print(f"   ⏸️  WordsAPI: Skipped (no API key)")
    
    # Test Wordnik if key is provided
    if WORDNIK_API_KEY:
        result = lookup_definition_wordnik(test_word, logger)
        if result:
            print(f"   ✅ Wordnik API: Working")
        else:
            print(f"   ❌ Wordnik API: Failed (check your API key)")
    else:
        print(f"   ⏸️  Wordnik API: Skipped (no API key)")
    
    print(f"   💡 Run this test anytime by calling test_apis()")
def lookup_definitions_for_batch(words, max_count=100, logger=None):
    """
    Look up definitions for a batch of words from dictionary API.
    Strategy: Take first 100 + last 100 words (likely common) + random words for variety.
    Returns list of tuples: (word_elem, word_text, definition, pos)
    """
    definitions_found = []
    
    if logger:
        logger.info(f"Looking up definitions for up to {max_count} words from dictionary API")
    
    word_list = list(words)
    
    # Strategy: Check up to 5000 words for better coverage
    max_words_to_check = 5000
    words_to_check = []
    
    # First 100 words (alphabetically early - often common words)
    if len(word_list) >= 100:
        first_100 = word_list[:100]
        words_to_check.extend(first_100)
        print(f"   📝 Selected first 100 undefined words (alphabetically early)")
    
    # Last 100 words (alphabetically late - often common words)
    if len(word_list) >= 200:
        last_100 = word_list[-100:]
        words_to_check.extend(last_100)
        print(f"   📝 Selected last 100 undefined words (alphabetically late)")
    elif len(word_list) >= 100:
        # If we have 100-199 words, take the second half
        second_half = word_list[len(word_list)//2:]
        words_to_check.extend(second_half)
        print(f"   📝 Selected last {len(second_half)} undefined words")
    
    # Add random words for variety (up to ~4800 more)
    remaining_words = []
    if len(word_list) > 200:
        # Exclude first 100 and last 100 from random selection
        remaining_words = word_list[100:-100]
    elif len(word_list) > 100:
        # Exclude first 100 only
        remaining_words = word_list[100:]
    
    if remaining_words:
        remaining_slots = max_words_to_check - len(words_to_check)
        if remaining_slots > 0:
            random_sample_size = min(remaining_slots, len(remaining_words))
            random_words = random.sample(remaining_words, random_sample_size)
            words_to_check.extend(random_words)
            print(f"   🎲 Added {random_sample_size} random words for variety")
    
    # If we have very few words total, just use them all
    if len(word_list) <= 200:
        words_to_check = word_list
        print(f"   📝 Using all {len(word_list)} remaining undefined words")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_words = []
    for item in words_to_check:
        word_text = item[1]
        if word_text not in seen:
            seen.add(word_text)
            unique_words.append(item)
    
    print(f"   🔍 Checking {len(unique_words)} unique words total (targeting {max_count} definitions)")
    
    processed = 0
    for word_elem, word_text in unique_words:
        if len(definitions_found) >= max_count:
            break
        
        processed += 1
        
        # Show progress more frequently due to higher volume
        if processed % 50 == 0:
            print(f"   📖 Processed {processed} words, found {len(definitions_found)} definitions...")
        
        result = lookup_definition(word_text, logger)
        if result:
            definition, pos = result
            definitions_found.append((word_elem, word_text, definition, pos))
            
            if logger and len(definitions_found) % 25 == 0:
                logger.info(f"Found {len(definitions_found)} definitions so far...")
        
        # Slightly faster pace due to higher volume, but still respectful
        time.sleep(0.05)
        
        # Stop if we've found enough definitions
        if len(definitions_found) >= max_count:
            break
    
    hit_rate = (len(definitions_found) / processed * 100) if processed > 0 else 0
    print(f"   ✅ Success rate: {len(definitions_found)}/{processed} ({hit_rate:.1f}%)")
    
    if logger:
        logger.info(f"Successfully found {len(definitions_found)} definitions from {processed} words checked")
    
    return definitions_found

def create_backup(words_path, backup_path, logger):
    """Create backup of existing word list before modifications."""
    if not words_path.exists():
        return True
    
    try:
        shutil.copy2(words_path, backup_path)
        logger.info(f"Backup created: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return False

def restore_backup(words_path, backup_path, logger):
    """Restore the backup file to words.txt"""
    if not backup_path.exists():
        logger.error("No backup file found to restore")
        return False
    
    try:
        shutil.copy2(backup_path, words_path)
        logger.info(f"Backup restored from {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        return False

def download_with_progress(url, logger, retry_attempts=RETRY_ATTEMPTS):
    """Downloads content from URL with progress display and retry logic."""
    for attempt in range(retry_attempts):
        try:
            logger.info(f"Downloading from {url} (attempt {attempt + 1}/{retry_attempts})")
            
            response = urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT)
            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            data = b''
            milestones = {1, 50, 100}
            hit = set()
            
            start_time = time.time()
            last_update = start_time

            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                downloaded += len(chunk)
                data += chunk
                
                current_time = time.time()
                if total and (current_time - last_update >= 0.1):
                    pct = (downloaded * 100) // total
                    speed = downloaded / (current_time - start_time) / 1024
                    print(f"\rDownloading: {pct}% ({downloaded:,}/{total:,} bytes) - {speed:.1f} KB/s", end='')
                    last_update = current_time
                    
                    if pct in milestones and pct not in hit:
                        logger.info(f"PROGRESS|{pct}%|{downloaded}/{total} bytes")
                        hit.add(pct)
            
            print()
            
            if 100 not in hit and total:
                logger.info(f"PROGRESS|100%|{downloaded}/{total} bytes")
            
            elapsed = time.time() - start_time
            logger.info(f"Download successful|{len(data)} bytes in {elapsed:.1f}s")
            
            return data.decode('utf-8')
            
        except urllib.error.URLError as e:
            logger.error(f"Download attempt {attempt + 1} failed: {e}")
            if attempt < retry_attempts - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("All download attempts failed")
                return None
        except Exception as e:
            logger.error(f"Unexpected download error: {e}")
            return None

def validate_words(words, logger):
    """Validate downloaded words for data integrity."""
    valid_words = []
    invalid_count = 0
    
    for word in words:
        if word and word.replace("'", "").replace("-", "").isalpha():
            valid_words.append(word.lower())
        else:
            invalid_count += 1
    
    if invalid_count > 0:
        logger.warning(f"Filtered out {invalid_count} invalid entries")
    
    return valid_words

def update_word_list(existing_words, new_words, words_path, logger):
    """Update word list with better error handling."""
    try:
        existing_set = set(existing_words)
        new_set = set(new_words)
        
        additions = new_set - existing_set
        deletions = existing_set - new_set
        
        if deletions:
            logger.warning(f"{len(deletions)} words removed from source")
        
        if not additions and not deletions:
            logger.info("No changes detected in word list")
            return len(existing_words)
        
        if len(new_set) < len(existing_set) * 0.9:
            logger.warning(f"New word list is significantly smaller ({len(new_set)} vs {len(existing_set)})")
            response = input(f"New list has {len(existing_set) - len(new_set)} fewer words. Continue? (y/n): ")
            if response.lower() != 'y':
                logger.info("User cancelled update due to size reduction")
                return -2
        
        all_words = sorted(new_set)
        
        temp_path = words_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            for word in all_words:
                f.write(word + '\n')
        
        temp_path.replace(words_path)
        
        logger.info(f"Updated dictionary: {len(additions)} added, {len(deletions)} removed")
        logger.info(f"Final word count: {len(all_words)}")
        
        return len(all_words)
        
    except Exception as e:
        logger.error(f"Failed to update word list: {e}")
        return -1

def fetch_words(logger):
    """Fetch and update word list from ENABLE dictionary."""
    try:
        logger.info("=== FETCH WORDS OPERATION ===")
        base_dir, data_dir, words_path, xml_path, backup_path = get_file_paths()
        
        logger.info(f"Working directory: {base_dir}")
        logger.info(f"Dictionary path: {words_path}")
        
        original_word_count = 0
        
        if words_path.exists():
            try:
                with open(words_path, 'r', encoding='utf-8') as f:
                    original_word_count = sum(1 for line in f if line.strip())
                logger.info(f"Original dictionary has {original_word_count} words")
            except Exception as e:
                logger.error(f"Failed to count existing words: {e}")
            
            if not create_backup(words_path, backup_path, logger):
                response = input("Failed to create backup. Continue anyway? (y/n): ")
                if response.lower() != 'y':
                    logger.info("User aborted due to backup failure")
                    return False

        existing = []
        if words_path.exists():
            try:
                with open(words_path, 'r', encoding='utf-8') as f:
                    existing = [w.strip().lower() for w in f if w.strip()]
                logger.info(f"Loaded {len(existing)} existing words")
            except Exception as e:
                logger.error(f"Failed to read existing dictionary: {e}")
                return False
        else:
            logger.info("No existing dictionary found, creating new one")

        content = download_with_progress(ENABLE_URL, logger)
        if not content:
            logger.error("Download failed; attempting to restore backup")
            if backup_path.exists() and restore_backup(words_path, backup_path, logger):
                logger.info("Successfully restored from backup after download failure")
            return False
        
        downloaded_words = [w.strip() for w in content.splitlines() if w.strip()]
        downloaded_words = validate_words(downloaded_words, logger)
        logger.info(f"Downloaded {len(downloaded_words)} valid words")

        if len(downloaded_words) == len(existing) and set(downloaded_words) == set(existing):
            logger.info("Dictionary is up to date (identical content)")
            return True

        result = update_word_list(existing, downloaded_words, words_path, logger)
        
        if result == -1:
            logger.error("Failed to update dictionary, restoring backup")
            if backup_path.exists() and restore_backup(words_path, backup_path, logger):
                logger.info("Successfully restored from backup after update failure")
            return False
        elif result == -2:
            logger.info("Update cancelled by user, restoring backup")
            if backup_path.exists() and restore_backup(words_path, backup_path, logger):
                logger.info("Successfully restored from backup after user cancellation")
            return True
        
        logger.info("Fetch operation completed successfully")
        print(f"\nDictionary updated: {result:,} total words")
        return True
        
    except Exception as e:
        logger.error(f"Fetch operation failed: {e}")
        return False

def convert_to_xml(logger):
    """Convert words.txt to dictionary.xml format, preserving existing definitions."""
    try:
        logger.info("=== CONVERT TO XML OPERATION ===")
        base_dir, data_dir, words_path, xml_path, backup_path = get_file_paths()
        
        if not words_path.exists():
            logger.error(f"Input file not found: {words_path}")
            return False
        
        with open(words_path, 'r', encoding='utf-8') as f:
            new_words = [line.strip() for line in f if line.strip()]
        
        logger.info(f"Loaded {len(new_words)} words from {words_path}")
        
        if not new_words:
            logger.error("No words found in input file")
            return False
        
        # Check if XML already exists and has definitions
        existing_definitions = {}
        words_with_definitions = 0
        
        if xml_path.exists():
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                
                if root.tag == "dictionary":
                    for word_elem in root.findall("word"):
                        # Extract word text
                        text_elem = word_elem.find("text")
                        if text_elem is not None:
                            word_text = text_elem.text
                        else:
                            word_text = word_elem.text
                        
                        if word_text:
                            word_text = word_text.strip().lower()
                            
                            # Check if it has definition
                            def_elem = word_elem.find("definition")
                            pos_elem = word_elem.find("pos")
                            
                            if def_elem is not None and pos_elem is not None:
                                definition = def_elem.text
                                pos = pos_elem.text
                                if definition and pos:
                                    existing_definitions[word_text] = (definition, pos)
                                    words_with_definitions += 1
                
                logger.info(f"Found {words_with_definitions} existing definitions to preserve")
                print(f"   📚 Preserving {words_with_definitions} existing definitions")
                
            except Exception as e:
                logger.warning(f"Could not parse existing XML, starting fresh: {e}")
                existing_definitions = {}
        
        # Create new XML structure
        root = ET.Element("dictionary")
        
        preserved_count = 0
        new_word_count = 0
        
        for word in new_words:
            word_lower = word.lower()
            word_element = ET.SubElement(root, "word")
            
            # Check if we have existing definition for this word
            if word_lower in existing_definitions:
                # Preserve existing definition
                definition, pos = existing_definitions[word_lower]
                
                text_elem = ET.SubElement(word_element, "text")
                text_elem.text = word
                
                def_elem = ET.SubElement(word_element, "definition")
                def_elem.text = definition
                
                pos_elem = ET.SubElement(word_element, "pos")
                pos_elem.text = pos
                
                preserved_count += 1
            else:
                # New word without definition
                word_element.text = word
                new_word_count += 1
        
        # Create pretty-printed XML
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="    ")
        
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        logger.info(f"Successfully created {xml_path}")
        logger.info(f"XML contains {len(new_words)} words: {preserved_count} with definitions, {new_word_count} without")
        print(f"\nXML conversion completed: {len(new_words):,} words")
        print(f"  📚 Preserved definitions: {preserved_count:,}")
        print(f"  📝 New words: {new_word_count:,}")
        
        return True
        
    except Exception as e:
        logger.error(f"Convert operation failed: {e}")
        return False

def add_definitions(logger):
    """Add AI-generated definitions and parts of speech to words in dictionary.xml."""
    try:
        logger.info("=== ADD DEFINITIONS OPERATION ===")
        base_dir, data_dir, words_path, xml_path, backup_path = get_file_paths()
        
        if not xml_path.exists():
            logger.error(f"XML file not found: {xml_path}")
            return False
        
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        if root.tag != "dictionary":
            logger.error("Root element is not <dictionary>")
            return False
        
        words_needing_definitions = []
        words_with_definitions = 0
        
        for word_elem in root.findall("word"):
            has_definition = word_elem.find("definition") is not None
            
            if has_definition:
                words_with_definitions += 1
                continue
            
            text_elem = word_elem.find("text")
            if text_elem is not None:
                word_text = text_elem.text
            else:
                word_text = word_elem.text
            
            if word_text and word_text.strip():
                words_needing_definitions.append((word_elem, word_text.strip().lower()))
        
        logger.info(f"Found {len(words_needing_definitions)} words without definitions")
        logger.info(f"Found {words_with_definitions} words already with definitions")
        
        print(f"\n📊 Definition Status:")
        print(f"   • Total words in dictionary: {len(root.findall('word')):,}")
        print(f"   • Words with definitions: {words_with_definitions:,}")
        print(f"   • Words without definitions: {len(words_needing_definitions):,}")
        print(f"   • Words we can define this run: {min(len(words_needing_definitions), 100):,}")
        
        if len(words_needing_definitions) == 0:
            print(f"\n🎉 All words have been defined!")
            return True

        print(f"\n📖 Looking up definitions from multiple dictionary APIs...")
        
        # Test APIs first
        test_apis(logger)
        
        # Show which APIs are available
        available_apis = ["Free Dictionary API (dictionaryapi.dev)"]
        if RAPIDAPI_KEY:
            available_apis.append("WordsAPI (2500/day)")
        if WORDNIK_API_KEY:
            available_apis.append("Wordnik API")
        
        print(f"\n   🔗 Available APIs: {', '.join(available_apis)}")
        if not RAPIDAPI_KEY:
            print(f"   💡 Get RapidAPI key for WordsAPI: https://rapidapi.com/dpventures/api/wordsapi")
        if not WORDNIK_API_KEY:
            print(f"   💡 Get Wordnik API key: https://developer.wordnik.com/")
        
        api_definitions = lookup_definitions_for_batch(words_needing_definitions, 100, logger)
        words_to_process = api_definitions
        
        logger.info(f"Adding definitions to {len(words_to_process)} words")
        
        if not words_to_process:
            logger.info("No definitions found from dictionary API for any words")
            print(f"\n📝 No definitions found!")
            print(f"   • The dictionary API didn't have definitions for the words checked")
            print(f"   • This can happen with very uncommon or specialized words")
            print(f"   • Try running again - different words will be checked")
            return True
        
        for word_elem, word_text, definition, pos in words_to_process:
            if word_elem.find("text") is None and word_elem.text:
                old_text = word_elem.text
                word_elem.text = None
                word_elem.tail = word_elem.tail
                
                text_elem = ET.SubElement(word_elem, "text")
                text_elem.text = old_text
            
            def_elem = ET.SubElement(word_elem, "definition")
            def_elem.text = definition
            
            pos_elem = ET.SubElement(word_elem, "pos")
            pos_elem.text = pos
        
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="    ")
        
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        logger.info(f"Successfully updated {xml_path}")
        logger.info(f"Added {len(words_to_process)} dictionary definitions")
        print(f"\n📖 Dictionary definitions added: {len(words_to_process)} words enhanced")
        
        if len(words_to_process) < 100 and len(words_needing_definitions) > len(words_to_process):
            remaining = len(words_needing_definitions) - len(words_to_process)
            print(f"   ℹ️  {remaining} words couldn't be found in any dictionary API")
            print(f"   💡 Try running again - different words will be checked")
            if not RAPIDAPI_KEY:
                print(f"   🚀 Add a RapidAPI key to unlock 2500 more lookups/day!")
            if not WORDNIK_API_KEY:
                print(f"   🚀 Add a Wordnik API key for even more coverage!")
        
        return True
        
    except Exception as e:
        logger.error(f"Add definitions operation failed: {e}")
        return False

def run_all_operations(logger):
    """Run all operations in sequence: fetch -> convert -> define"""
    logger.info("=== RUNNING ALL OPERATIONS ===")
    
    operations = [
        ("Fetching words", fetch_words),
        ("Converting to XML", convert_to_xml),
        ("Adding definitions", add_definitions)
    ]
    
    for operation_name, operation_func in operations:
        print(f"\n{operation_name}...")
        if not operation_func(logger):
            logger.error(f"Operation failed: {operation_name}")
            return False
        print(f"{operation_name} completed successfully!")
    
    logger.info("All operations completed successfully")
    return True

def show_menu():
    """Display interactive menu and get user choice."""
    print("\n" + "="*50)
    print("        DICTIONARY MANAGEMENT TOOLS")
    print("="*50)
    print()
    print("Please select an operation:")
    print()
    print("  1. Fetch Words    - Download/update word list from ENABLE")
    print("  2. Convert XML    - Convert words.txt to dictionary.xml")
    print("  3. Add Definitions- Add real dictionary definitions to 100 words")
    print("  4. Run All        - Execute all operations in sequence")
    print("  5. Exit           - Quit the program")
    print()
    print("-" * 50)
    
    while True:
        try:
            choice = input("Enter your choice (1-5): ").strip()
            
            if choice == '1':
                return 'fetch'
            elif choice == '2':
                return 'convert'
            elif choice == '3':
                return 'define'
            elif choice == '4':
                return 'all'
            elif choice == '5':
                return 'exit'
            else:
                print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")
                
        except (EOFError, KeyboardInterrupt):
            print("\n\nExiting...")
            return 'exit'

def execute_command(command, logger):
    """Execute the specified command and return success status."""
    if command == 'fetch':
        print("\n🔄 Fetching words from ENABLE dictionary...")
        return fetch_words(logger)
    elif command == 'convert':
        print("\n🔄 Converting words.txt to dictionary.xml...")
        return convert_to_xml(logger)
    elif command == 'define':
        print("\n🔄 Adding real dictionary definitions...")
        return add_definitions(logger)
    elif command == 'all':
        print("\n🔄 Running all operations...")
        return run_all_operations(logger)
    else:
        logger.error(f"Unknown command: {command}")
        return False

def main():
    """Main function with both command-line and interactive menu support."""
    if len(sys.argv) > 1:
        # Command-line mode
        parser = argparse.ArgumentParser(
            description="Dictionary Management Tools",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Commands:
  fetch     Download/update word list from ENABLE
  convert   Convert words.txt to dictionary.xml
  define    Add real dictionary definitions to 100 words in dictionary.xml
  all       Run all commands in sequence
            """
        )
        parser.add_argument(
            'command', 
            choices=['fetch', 'convert', 'define', 'all'],
            help='Command to execute'
        )
        
        args = parser.parse_args()
        command = args.command
        
        logger = setup_logging()
        
        print("Dictionary Management Tools")
        print("===========================")
        
        try:
            success = execute_command(command, logger)
            
            if success:
                print(f"\n✓ Operation '{command}' completed successfully!")
                return 0
            else:
                print(f"\n✗ Operation '{command}' failed!")
                return 1
                
        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            print("\n\nOperation cancelled by user.")
            return 130
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            print(f"\nUnexpected error: {e}")
            return 1
    
    else:
        # Interactive menu mode
        logger = setup_logging()
        
        try:
            while True:
                command = show_menu()
                
                if command == 'exit':
                    print("\nGoodbye! 👋")
                    logger.info("Program exited by user")
                    return 0
                
                success = execute_command(command, logger)
                
                if success:
                    print(f"\n✅ Operation '{command}' completed successfully!")
                else:
                    print(f"\n❌ Operation '{command}' failed!")
                
                print("\n" + "-" * 50)
                continue_choice = input("Would you like to perform another operation? (y/n): ").strip().lower()
                
                if continue_choice not in ['y', 'yes']:
                    print("\nGoodbye! 👋")
                    logger.info("Program exited by user")
                    return 0
                    
        except KeyboardInterrupt:
            logger.info("Program interrupted by user")
            print("\n\nGoodbye! 👋")
            return 130
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            return 1

if __name__ == '__main__':
    sys.exit(main())