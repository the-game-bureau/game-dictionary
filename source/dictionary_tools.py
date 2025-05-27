#!/usr/bin/env python3
"""
Simplified Dictionary Management Tools

This script provides two main functions:
1. Download and maintain the ENABLE word list (word_fetcher functionality)
2. Convert words.txt to dictionary.xml format (xml_converter functionality)  

Usage:
  python dictionary_tools.py [command]
  
Commands:
  fetch     - Download/update word list from ENABLE
  convert   - Convert words.txt to dictionary.xml
  all       - Run all commands in sequence (fetch -> convert)
  
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
import argparse

# Configuration constants
DOWNLOAD_TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5
CHUNK_SIZE = 8192
ENABLE_URL = "https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt"

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
        
        # Check if XML already exists and preserve existing definitions
        existing_definitions = {}
        words_with_definitions = 0
        
        if xml_path.exists():
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                
                if root.tag == "dictionary":
                    for word_elem in root.findall("word"):
                        # Check if this word has definitions (has child elements)
                        if len(word_elem) > 0:
                            # Extract word text
                            text_elem = word_elem.find("text")
                            if text_elem is not None:
                                word_text = text_elem.text
                            else:
                                word_text = word_elem.text
                            
                            if word_text:
                                word_text = word_text.strip().lower()
                                # Store the entire element structure for words with definitions
                                existing_definitions[word_text] = word_elem
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
            
            # Check if we have existing definition for this word
            if word_lower in existing_definitions:
                # Copy the existing element with all its structure
                existing_elem = existing_definitions[word_lower]
                new_elem = ET.SubElement(root, "word")
                
                # Copy all attributes
                new_elem.attrib = existing_elem.attrib.copy()
                
                # Copy text content if it exists
                if existing_elem.text:
                    new_elem.text = existing_elem.text
                
                # Copy all child elements
                for child in existing_elem:
                    new_child = ET.SubElement(new_elem, child.tag)
                    new_child.text = child.text
                    new_child.attrib = child.attrib.copy()
                    if child.tail:
                        new_child.tail = child.tail
                
                # Copy tail if it exists
                if existing_elem.tail:
                    new_elem.tail = existing_elem.tail
                
                preserved_count += 1
            else:
                # New word without definition - simple structure
                word_element = ET.SubElement(root, "word")
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

def run_all_operations(logger):
    """Run all operations in sequence: fetch -> convert"""
    logger.info("=== RUNNING ALL OPERATIONS ===")
    
    operations = [
        ("Fetching words", fetch_words),
        ("Converting to XML", convert_to_xml)
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
    print("  3. Run All        - Execute all operations in sequence")
    print("  4. Exit           - Quit the program")
    print()
    print("-" * 50)
    
    while True:
        try:
            choice = input("Enter your choice (1-4): ").strip()
            
            if choice == '1':
                return 'fetch'
            elif choice == '2':
                return 'convert'
            elif choice == '3':
                return 'all'
            elif choice == '4':
                return 'exit'
            else:
                print("Invalid choice. Please enter 1, 2, 3, or 4.")
                
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
  all       Run all commands in sequence
            """
        )
        parser.add_argument(
            'command', 
            choices=['fetch', 'convert', 'all'],
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