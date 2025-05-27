#!/usr/bin/env python3
"""
High-Volume Dictionary Definition Tool

A standalone script focused on adding real dictionary definitions to large numbers of words.
Optimized for processing up to 10,000 words efficiently with robust API handling.

Usage:
  python word_definer.py [options]
  
Options:
  --count N         Number of definitions to add (default: 10000)
  --input FILE      Input XML file (default: data/dictionary.xml)
  --output FILE     Output XML file (default: overwrites input)
  --strategy STR    Word selection strategy (default: smart)
  --delay FLOAT     Delay between API calls in seconds (default: 0.05)
  --batch-size N    Progress reporting interval (default: 100)
  --dry-run         Show what would be processed without making changes
  --resume          Resume from where last run left off
  --test-apis       Test all configured APIs and exit

Strategies:
  smart      - Mix of common words (first/last) + random sample
  random     - Pure random selection from undefined words
  sequential - Process words in alphabetical order
  short      - Prioritize shorter words (2-8 characters)
  long       - Prioritize longer words (9+ characters)

Features:
  - Multiple API fallbacks (Free Dictionary, WordsAPI, Wordnik)
  - Smart rate limiting and error handling
  - Progress tracking and resume capability
  - Detailed statistics and reporting
  - Memory-efficient processing of large datasets
  - Automatic backup creation

Requirements:
  - Python 3.x
  - Internet connection
  - data/dictionary.xml file (from dictionary_tools.py)

API Keys (optional but recommended):
  Set RAPIDAPI_KEY for WordsAPI (2500 requests/day)
  Set WORDNIK_API_KEY for Wordnik API (additional requests)
"""

import sys
import urllib.request
import urllib.error
from pathlib import Path
import logging
import time
import json
import random
import xml.etree.ElementTree as ET
from xml.dom import minidom
import argparse
import shutil
from datetime import datetime, timedelta
import os
from collections import defaultdict
import signal

# API Configuration
DICTIONARY_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/"
WORDSAPI_URL = "https://wordsapiv1.p.rapidapi.com/words/"
WORDNIK_API_URL = "https://api.wordnik.com/v4/word.json/"

# Get API keys from environment or set here
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY', '87eb0e8b54mshcc502a511d6339ep1290f4jsne647be278143')
WORDNIK_API_KEY = os.getenv('WORDNIK_API_KEY', None)

# Performance settings
API_TIMEOUT = 15
DEFAULT_DELAY = 0.05
MAX_RETRIES = 3
BATCH_SIZE = 100

class DefinitionStats:
    """Track statistics for the definition lookup process."""
    
    def __init__(self):
        self.start_time = time.time()
        self.total_processed = 0
        self.definitions_found = 0
        self.api_stats = defaultdict(int)
        self.error_stats = defaultdict(int)
        self.words_per_minute = 0
        self.estimated_completion = None
        self.last_update = time.time()
    
    def update(self, processed, found, api_name=None, error_type=None):
        """Update statistics."""
        self.total_processed = processed
        self.definitions_found = found
        
        if api_name:
            self.api_stats[api_name] += 1
        
        if error_type:
            self.error_stats[error_type] += 1
        
        # Calculate rates
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.words_per_minute = (processed / elapsed) * 60
    
    def estimate_completion(self, remaining_words):
        """Estimate completion time."""
        if self.words_per_minute > 0:
            minutes_remaining = remaining_words / self.words_per_minute
            completion_time = datetime.now() + timedelta(minutes=minutes_remaining)
            self.estimated_completion = completion_time
    
    def get_summary(self):
        """Get a summary of current statistics."""
        elapsed = time.time() - self.start_time
        success_rate = (self.definitions_found / self.total_processed * 100) if self.total_processed > 0 else 0
        
        summary = {
            'elapsed_time': elapsed,
            'total_processed': self.total_processed,
            'definitions_found': self.definitions_found,
            'success_rate': success_rate,
            'words_per_minute': self.words_per_minute,
            'estimated_completion': self.estimated_completion,
            'api_usage': dict(self.api_stats),
            'errors': dict(self.error_stats)
        }
        
        return summary

class ProgressTracker:
    """Handle progress tracking and resume functionality."""
    
    def __init__(self, progress_file="data/definition_progress.json"):
        self.progress_file = Path(progress_file)
        self.processed_words = set()
        self.last_save = time.time()
        self.save_interval = 60  # Save every minute
    
    def load_progress(self):
        """Load progress from previous run."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    self.processed_words = set(data.get('processed_words', []))
                    return len(self.processed_words)
            except Exception as e:
                print(f"Warning: Could not load progress file: {e}")
        return 0
    
    def save_progress(self):
        """Save current progress."""
        try:
            self.progress_file.parent.mkdir(exist_ok=True)
            data = {
                'processed_words': list(self.processed_words),
                'last_updated': datetime.now().isoformat(),
                'total_processed': len(self.processed_words)
            }
            with open(self.progress_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save progress: {e}")
    
    def mark_processed(self, word):
        """Mark a word as processed."""
        self.processed_words.add(word.lower())
        
        # Periodic save
        if time.time() - self.last_save > self.save_interval:
            self.save_progress()
            self.last_save = time.time()
    
    def is_processed(self, word):
        """Check if word has been processed."""
        return word.lower() in self.processed_words
    
    def cleanup(self):
        """Clean up progress file."""
        if self.progress_file.exists():
            try:
                self.progress_file.unlink()
            except Exception:
                pass

def setup_logging(log_file="logs/word_definer.log"):
    """Set up logging for the word definer."""
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s|%(levelname)s|%(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
        handlers=[
            logging.FileHandler(log_path, mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def lookup_definition_free_dict(word, logger=None):
    """Look up definition from Free Dictionary API."""
    try:
        url = f"{DICTIONARY_API_URL}{word.lower()}"
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'WordDefiner/2.0')
        
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
            return (definition, part_of_speech, 'free_dict')
        
        return None
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        else:
            if logger:
                logger.debug(f"Free Dict API HTTP {e.code} for '{word}'")
            return None
    except Exception as e:
        if logger:
            logger.debug(f"Free Dict API error for '{word}': {e}")
        return None

def lookup_definition_wordsapi(word, logger=None):
    """Look up definition from WordsAPI."""
    if not RAPIDAPI_KEY:
        return None
        
    try:
        url = f"{WORDSAPI_URL}{word.lower()}"
        request = urllib.request.Request(url)
        request.add_header('X-RapidAPI-Key', RAPIDAPI_KEY)
        request.add_header('X-RapidAPI-Host', 'wordsapiv1.p.rapidapi.com')
        request.add_header('User-Agent', 'WordDefiner/2.0')
        
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
            return (definition, part_of_speech, 'wordsapi')
        
        return None
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        elif e.code in [401, 403, 429]:
            if logger:
                logger.warning(f"WordsAPI rate limit/auth error {e.code}")
            return None
        else:
            if logger:
                logger.debug(f"WordsAPI HTTP {e.code} for '{word}'")
            return None
    except Exception as e:
        if logger:
            logger.debug(f"WordsAPI error for '{word}': {e}")
        return None

def lookup_definition_wordnik(word, logger=None):
    """Look up definition from Wordnik API."""
    if not WORDNIK_API_KEY:
        return None
        
    try:
        url = f"{WORDNIK_API_URL}{word.lower()}/definitions?limit=1&includeRelated=false&sourceDictionaries=all&useCanonical=false&includeTags=false&api_key={WORDNIK_API_KEY}"
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'WordDefiner/2.0')
        
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
            return (definition, part_of_speech, 'wordnik')
        
        return None
        
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        else:
            if logger:
                logger.debug(f"Wordnik API HTTP {e.code} for '{word}'")
            return None
    except Exception as e:
        if logger:
            logger.debug(f"Wordnik API error for '{word}': {e}")
        return None

def lookup_definition(word, logger=None):
    """Look up definition using multiple APIs with smart retry logic."""
    apis = [
        ("free_dict", lookup_definition_free_dict),
        ("wordsapi", lookup_definition_wordsapi),
        ("wordnik", lookup_definition_wordnik),
    ]
    
    for api_name, api_func in apis:
        for attempt in range(MAX_RETRIES):
            try:
                result = api_func(word, logger)
                if result:
                    return result
                break  # No need to retry if we got a response (even if empty)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    if logger:
                        logger.debug(f"API {api_name} failed for '{word}' after {MAX_RETRIES} attempts")
                    break
        
        # Small delay between different APIs
        time.sleep(0.05)
    
    return None

def test_apis(logger):
    """Test all configured APIs."""
    test_words = ["hello", "computer", "amazing"]
    print("\n🧪 Testing APIs...")
    
    results = {}
    
    # Test Free Dictionary API
    working = 0
    for word in test_words:
        if lookup_definition_free_dict(word, logger):
            working += 1
    results['Free Dictionary'] = f"{working}/{len(test_words)} words found"
    
    # Test WordsAPI
    if RAPIDAPI_KEY:
        working = 0
        for word in test_words:
            if lookup_definition_wordsapi(word, logger):
                working += 1
        results['WordsAPI'] = f"{working}/{len(test_words)} words found"
    else:
        results['WordsAPI'] = "Skipped (no API key)"
    
    # Test Wordnik
    if WORDNIK_API_KEY:
        working = 0
        for word in test_words:
            if lookup_definition_wordnik(word, logger):
                working += 1
        results['Wordnik'] = f"{working}/{len(test_words)} words found"
    else:
        results['Wordnik'] = "Skipped (no API key)"
    
    for api, result in results.items():
        status = "✅" if "words found" in result and not result.startswith("0/") else "⏸️" if "Skipped" in result else "❌"
        print(f"   {status} {api}: {result}")
    
    return results

def get_words_needing_definitions(xml_path, logger):
    """Get all words that need definitions from XML file."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    words_needing_definitions = []
    words_with_definitions = 0
    
    for word_elem in root.findall("word"):
        has_definition = word_elem.find("definition") is not None
        
        if has_definition:
            words_with_definitions += 1
            continue
        
        # Get word text
        text_elem = word_elem.find("text")
        if text_elem is not None:
            word_text = text_elem.text
        else:
            word_text = word_elem.text
        
        if word_text and word_text.strip():
            words_needing_definitions.append((word_elem, word_text.strip()))
    
    logger.info(f"Found {len(words_needing_definitions)} words needing definitions")
    logger.info(f"Found {words_with_definitions} words already with definitions")
    
    return words_needing_definitions, words_with_definitions

def select_words_by_strategy(words_list, strategy, count, logger):
    """Select words based on the chosen strategy."""
    if len(words_list) <= count:
        logger.info(f"Selecting all {len(words_list)} available words")
        return words_list
    
    logger.info(f"Selecting {count} words using '{strategy}' strategy from {len(words_list)} candidates")
    
    if strategy == "sequential":
        return words_list[:count]
    
    elif strategy == "random":
        return random.sample(words_list, count)
    
    elif strategy == "short":
        # Sort by length (ascending), then alphabetically
        sorted_words = sorted(words_list, key=lambda x: (len(x[1]), x[1]))
        return sorted_words[:count]
    
    elif strategy == "long":
        # Sort by length (descending), then alphabetically
        sorted_words = sorted(words_list, key=lambda x: (-len(x[1]), x[1]))
        return sorted_words[:count]
    
    elif strategy == "smart":
        # Smart strategy: mix of common positions + random
        selected = []
        
        # Take first 20% (alphabetically early - often common)
        first_chunk = min(count // 5, len(words_list) // 10)
        if first_chunk > 0:
            selected.extend(words_list[:first_chunk])
        
        # Take last 20% (alphabetically late - also often common)
        last_chunk = min(count // 5, len(words_list) // 10)
        if last_chunk > 0 and len(words_list) > first_chunk:
            selected.extend(words_list[-last_chunk:])
        
        # Fill remaining with random selection
        remaining_needed = count - len(selected)
        if remaining_needed > 0:
            # Exclude already selected words from random pool
            available_for_random = [w for w in words_list if w not in selected]
            if available_for_random:
                random_count = min(remaining_needed, len(available_for_random))
                selected.extend(random.sample(available_for_random, random_count))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_selected = []
        for item in selected:
            if item[1] not in seen:
                seen.add(item[1])
                unique_selected.append(item)
        
        return unique_selected[:count]
    
    else:
        logger.warning(f"Unknown strategy '{strategy}', using random")
        return random.sample(words_list, count)

def process_words_for_definitions(words_to_process, delay, stats, progress, logger, dry_run=False):
    """Process words to add definitions."""
    if dry_run:
        print(f"\n🔍 DRY RUN: Would process {len(words_to_process)} words")
        for i, (word_elem, word_text) in enumerate(words_to_process[:10]):
            print(f"   {i+1}. {word_text}")
        if len(words_to_process) > 10:
            print(f"   ... and {len(words_to_process) - 10} more")
        return []
    
    definitions_found = []
    
    print(f"\n📖 Processing {len(words_to_process)} words for definitions...")
    
    for i, (word_elem, word_text) in enumerate(words_to_process, 1):
        # Skip if already processed (resume functionality)
        if progress.is_processed(word_text):
            continue
        
        # Look up definition
        result = lookup_definition(word_text, logger)
        
        # Update statistics
        if result:
            definition, pos, api_name = result
            definitions_found.append((word_elem, word_text, definition, pos))
            stats.update(i, len(definitions_found), api_name)
            logger.debug(f"Found definition for '{word_text}' via {api_name}")
        else:
            stats.update(i, len(definitions_found), error_type='not_found')
        
        # Mark as processed
        progress.mark_processed(word_text)
        
        # Progress reporting
        if i % BATCH_SIZE == 0 or i == len(words_to_process):
            elapsed = time.time() - stats.start_time
            remaining = len(words_to_process) - i
            stats.estimate_completion(remaining)
            
            print(f"   📊 Progress: {i}/{len(words_to_process)} ({i/len(words_to_process)*100:.1f}%) | "
                  f"Found: {len(definitions_found)} | "
                  f"Rate: {stats.words_per_minute:.1f}/min | "
                  f"Success: {len(definitions_found)/i*100:.1f}%")
            
            if stats.estimated_completion and remaining > 0:
                eta = stats.estimated_completion.strftime("%H:%M:%S")
                print(f"   ⏱️  ETA: {eta} ({remaining} words remaining)")
        
        # Rate limiting
        if delay > 0:
            time.sleep(delay)
    
    return definitions_found

def update_xml_with_definitions(xml_path, definitions, logger, backup=True):
    """Update XML file with new definitions."""
    if backup:
        backup_path = xml_path.with_suffix(f'.backup_{int(time.time())}')
        shutil.copy2(xml_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
    
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Add definitions to word elements
    for word_elem, word_text, definition, pos in definitions:
        # Convert simple word element to structured format if needed
        if word_elem.find("text") is None and word_elem.text:
            old_text = word_elem.text
            word_elem.text = None
            
            text_elem = ET.SubElement(word_elem, "text")
            text_elem.text = old_text
        
        # Add definition and part of speech
        def_elem = ET.SubElement(word_elem, "definition")
        def_elem.text = definition
        
        pos_elem = ET.SubElement(word_elem, "pos")
        pos_elem.text = pos
    
    # Pretty print and save
    rough_string = ET.tostring(root, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="    ")
    
    # Clean up empty lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    pretty_xml = '\n'.join(lines)
    
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    
    logger.info(f"Updated {xml_path} with {len(definitions)} new definitions")

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    print(f"\n\n⚠️  Received signal {signum}. Saving progress and exiting...")
    sys.exit(0)

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="High-Volume Dictionary Definition Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python word_definer.py                    # Add 10,000 definitions using smart strategy
  python word_definer.py --count 5000      # Add 5,000 definitions
  python word_definer.py --strategy random # Use random word selection
  python word_definer.py --dry-run         # Preview what would be processed
  python word_definer.py --test-apis       # Test API connectivity
  python word_definer.py --resume          # Resume from previous run
        """
    )
    
    parser.add_argument('--count', type=int, default=10000,
                        help='Number of definitions to add (default: 10000)')
    parser.add_argument('--input', type=str, default='data/dictionary.xml',
                        help='Input XML file (default: data/dictionary.xml)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output XML file (default: same as input)')
    parser.add_argument('--strategy', choices=['smart', 'random', 'sequential', 'short', 'long'],
                        default='smart', help='Word selection strategy (default: smart)')
    parser.add_argument('--delay', type=float, default=DEFAULT_DELAY,
                        help='Delay between API calls in seconds (default: 0.05)')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help='Progress reporting interval (default: 100)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without making changes')
    parser.add_argument('--resume', action='store_true',
                        help='Resume from where last run left off')
    parser.add_argument('--test-apis', action='store_true',
                        help='Test all configured APIs and exit')
    parser.add_argument('--no-backup', action='store_true',
                        help='Skip creating backup file')
    
    args = parser.parse_args()
    
    # Set up logging
    logger = setup_logging()
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("High-Volume Dictionary Definition Tool")
    print("=====================================")
    
    # Test APIs if requested
    if args.test_apis:
        test_apis(logger)
        return 0
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return 1
    
    output_path = Path(args.output) if args.output else input_path
    
    try:
        # Initialize progress tracking
        progress = ProgressTracker()
        if args.resume:
            previously_processed = progress.load_progress()
            if previously_processed > 0:
                print(f"📂 Resuming from previous run ({previously_processed} words already processed)")
        
        # Get words needing definitions
        logger.info(f"Loading words from {input_path}")
        words_needing_definitions, words_with_definitions = get_words_needing_definitions(input_path, logger)
        
        # Filter out already processed words if resuming
        if args.resume:
            original_count = len(words_needing_definitions)
            words_needing_definitions = [
                (elem, text) for elem, text in words_needing_definitions
                if not progress.is_processed(text)
            ]
            filtered_count = original_count - len(words_needing_definitions)
            if filtered_count > 0:
                print(f"   📋 Filtered out {filtered_count} already processed words")
        
        print(f"\n📊 Current Status:")
        print(f"   • Words with definitions: {words_with_definitions:,}")
        print(f"   • Words needing definitions: {len(words_needing_definitions):,}")
        print(f"   • Target for this run: {min(args.count, len(words_needing_definitions)):,}")
        
        if len(words_needing_definitions) == 0:
            print(f"\n🎉 All words already have definitions!")
            progress.cleanup()
            return 0
        
        # Select words based on strategy
        words_to_process = select_words_by_strategy(
            words_needing_definitions, args.strategy, args.count, logger
        )
        
        print(f"\n🎯 Selected {len(words_to_process)} words using '{args.strategy}' strategy")
        
        if args.dry_run:
            process_words_for_definitions(words_to_process, args.delay, None, progress, logger, dry_run=True)
            return 0
        
        # Test APIs before starting
        print(f"\n🔧 Configuration:")
        available_apis = ["Free Dictionary API"]
        if RAPIDAPI_KEY:
            available_apis.append("WordsAPI")
        if WORDNIK_API_KEY:
            available_apis.append("Wordnik API")
        print(f"   • Available APIs: {', '.join(available_apis)}")
        print(f"   • Rate limiting: {args.delay}s between calls")
        print(f"   • Progress updates: every {args.batch_size} words")
        
        api_test_results = test_apis(logger)
        
        # Initialize statistics
        stats = DefinitionStats()
        
        # Process words for definitions
        definitions_found = process_words_for_definitions(
            words_to_process, args.delay, stats, progress, logger
        )
        
        if definitions_found:
            print(f"\n💾 Updating XML file with {len(definitions_found)} new definitions...")
            update_xml_with_definitions(output_path, definitions_found, logger, backup=not args.no_backup)
            
            # Final statistics
            summary = stats.get_summary()
            print(f"\n📈 Final Results:")
            print(f"   • Total processed: {summary['total_processed']:,}")
            print(f"   • Definitions found: {summary['definitions_found']:,}")
            print(f"   • Success rate: {summary['success_rate']:.1f}%")
            print(f"   • Average rate: {summary['words_per_minute']:.1f} words/minute")
            print(f"   • Total time: {summary['elapsed_time']/60:.1f} minutes")
            
            if summary['api_usage']:
                print(f"   • API usage: {summary['api_usage']}")
            
            logger.info(f"Successfully added {len(definitions_found)} definitions")
            
            # Clean up progress file on successful completion
            if len(definitions_found) == len(words_to_process):
                progress.cleanup()
        else:
            print(f"\n😔 No definitions found for any of the processed words")
        
        return 0
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Operation cancelled by user")
        progress.save_progress()
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n❌ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())