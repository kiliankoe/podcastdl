import feedparser
import requests
import os
import re
from datetime import datetime
from tqdm import tqdm
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def sanitize_filename(filename):
    """Removes invalid characters from a filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def save_episode_metadata(episode_entry, output_path, episode_title, publish_date):
    """Saves episode metadata to a txt file alongside the episode."""
    try:
        safe_episode_title = sanitize_filename(episode_title)
        metadata_filename = f"{safe_episode_title}.txt"
        metadata_path = os.path.join(output_path, metadata_filename)
        
        # Skip if metadata file already exists
        if os.path.exists(metadata_path):
            return True
        
        # Extract available metadata
        metadata_lines = []
        metadata_lines.append(f"Title: {episode_entry.get('title', 'N/A')}")
        metadata_lines.append(f"Published: {publish_date.strftime('%Y-%m-%d %H:%M:%S') if publish_date != datetime.min else 'Unknown'}")
        
        # Short Description/Summary
        short_description = None
        if hasattr(episode_entry, 'description') and episode_entry.description:
            short_description = episode_entry.description
        elif hasattr(episode_entry, 'summary') and episode_entry.summary:
            short_description = episode_entry.summary
        
        if short_description:
            # Clean up HTML tags if present
            import html
            short_description = html.unescape(short_description)
            short_description = re.sub(r'<[^>]+>', '', short_description)  # Remove HTML tags
            short_description = re.sub(r'\s+', ' ', short_description).strip()  # Normalize whitespace
            metadata_lines.append(f"Description: {short_description}")
        
        # Store extended content for later (will be added at the end)
        extended_content = None
        if hasattr(episode_entry, 'content') and episode_entry.content:
            if isinstance(episode_entry.content, list) and len(episode_entry.content) > 0:
                extended_content = episode_entry.content[0].get('value', '')
            else:
                extended_content = str(episode_entry.content)
        
        # Author
        author = episode_entry.get('author', episode_entry.get('itunes_author', 'N/A'))
        if author:
            metadata_lines.append(f"Author: {author}")
        
        # Duration
        duration = episode_entry.get('itunes_duration', episode_entry.get('duration', 'N/A'))
        if duration:
            metadata_lines.append(f"Duration: {duration}")
        
        # Episode link/URL
        if hasattr(episode_entry, 'link') and episode_entry.link:
            metadata_lines.append(f"Episode URL: {episode_entry.link}")
        
        # iTunes episode number and season if available
        if hasattr(episode_entry, 'itunes_episode') and episode_entry.itunes_episode:
            metadata_lines.append(f"Episode Number: {episode_entry.itunes_episode}")
        if hasattr(episode_entry, 'itunes_season') and episode_entry.itunes_season:
            metadata_lines.append(f"Season: {episode_entry.itunes_season}")
        
        # Categories/Tags
        if hasattr(episode_entry, 'tags') and episode_entry.tags:
            tags = [tag.get('term', '') for tag in episode_entry.tags if tag.get('term')]
            if tags:
                metadata_lines.append(f"Tags: {', '.join(tags)}")
        
        # Extended Shownotes from content:encoded (add at the end)
        if extended_content:
            # Convert HTML to more readable text while preserving some structure
            import html
            extended_content = html.unescape(extended_content)
            
            # Convert common HTML elements to readable text
            extended_content = re.sub(r'<h([1-6]).*?>(.*?)</h[1-6]>', r'\n\n=== \2 ===\n', extended_content)  # Headers
            extended_content = re.sub(r'<li.*?>(.*?)</li>', r'  • \1\n', extended_content)  # List items
            extended_content = re.sub(r'<ul.*?>', '\n', extended_content)  # Start unordered list
            extended_content = re.sub(r'</ul>', '\n', extended_content)  # End unordered list
            extended_content = re.sub(r'<ol.*?>', '\n', extended_content)  # Start ordered list
            extended_content = re.sub(r'</ol>', '\n', extended_content)  # End ordered list
            extended_content = re.sub(r'<p.*?>', '\n', extended_content)  # Paragraphs
            extended_content = re.sub(r'</p>', '\n', extended_content)
            extended_content = re.sub(r'<br\s*/?>', '\n', extended_content)  # Line breaks
            extended_content = re.sub(r'<a.*?href=["\']([^"\']*)["\'].*?>(.*?)</a>', r'\2 (\1)', extended_content)  # Links
            
            # Remove remaining HTML tags
            extended_content = re.sub(r'<[^>]+>', '', extended_content)
            
            # Clean up whitespace
            extended_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', extended_content)  # Multiple newlines
            extended_content = re.sub(r'^\s+|\s+$', '', extended_content, flags=re.MULTILINE)  # Trim lines
            extended_content = extended_content.strip()
            
            if extended_content and extended_content != short_description:
                metadata_lines.append(f"\nExtended Shownotes:\n{extended_content}")
        
        # Write metadata file
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(metadata_lines))
            f.write('\n')
        
        return True
    except Exception as e:
        # Silently fail for metadata - don't let it break episode downloads
        return False

def download_episode(episode_url, output_path, episode_title):
    """Downloads a single episode with a progress bar."""
    try:
        response = requests.get(episode_url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024

        safe_episode_title = sanitize_filename(episode_title)
        file_extension = os.path.splitext(episode_url.split('?')[0])[-1]
        if not file_extension or len(file_extension) > 5 or len(file_extension) < 2:
            file_extension = ".mp3"

        filename = f"{safe_episode_title}{file_extension}"
        full_output_path = os.path.join(output_path, filename)

        if os.path.exists(full_output_path):
            if total_size > 0 and os.path.getsize(full_output_path) == total_size:
                return True, filename, True # Added flag for skipped

        with open(full_output_path, 'wb') as file, \
             tqdm(total=total_size, unit='iB', unit_scale=True, desc=safe_episode_title[:40].ljust(40), leave=False) as bar:
            for data in response.iter_content(block_size):
                bar.update(len(data))
                file.write(data)

        if total_size != 0 and os.path.getsize(full_output_path) != total_size:
            print(f"Error: Size mismatch for '{filename}'. Download may be incomplete.")
            if os.path.exists(full_output_path): # Clean up incomplete file
                 os.remove(full_output_path)
            return False, filename, False
        return True, filename, False # Not skipped
    except requests.exceptions.Timeout:
        print(f"Timeout occurred while trying to download {episode_url}")
        return False, None, False
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {episode_url}: {e}")
        return False, None, False
    except Exception as e:
        print(f"An unexpected error occurred while downloading '{episode_title}': {e}")
        return False, None, False

def download_podcast_episodes(feed_url, output_dir="podcast_episodes", max_concurrent=3):
    """
    Downloads all episodes from a podcast feed URL, oldest first,
    into the specified output directory.
    """
    print(f"Fetching feed from: {feed_url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 PodcastDownloader/1.0'}
        parsed_feed = feedparser.parse(feed_url, agent=headers.get('User-Agent'))
    except Exception as e:
        print(f"Error parsing feed: {e}")
        return

    if parsed_feed.bozo:
        bozo_reason = parsed_feed.bozo_exception if hasattr(parsed_feed.bozo_exception, 'getMessage') else parsed_feed.bozo_exception
        print(f"Warning: Feed may be malformed. Bozo reason: {bozo_reason}")


    if not parsed_feed.entries:
        print("No episodes found in the feed.")
        if parsed_feed.feed and 'title' in parsed_feed.feed:
             print(f"Podcast Title: {parsed_feed.feed.title}")
        else:
            print("Could not retrieve podcast title.")
        return

    if parsed_feed.feed and 'title' in parsed_feed.feed:
        podcast_title_sanitized = sanitize_filename(parsed_feed.feed.title)
        # If the default output_dir is used, append the podcast title to it
        if output_dir == "podcast_episodes" and podcast_title_sanitized:
            output_dir = os.path.join("podcast_episodes", podcast_title_sanitized)

    episodes = []
    for entry in parsed_feed.entries:
        publish_date = datetime.min
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            publish_date = datetime(*entry.published_parsed[:6])
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
             publish_date = datetime(*entry.updated_parsed[:6])
        episodes.append({'entry': entry, 'date': publish_date})

    sorted_episodes = sorted(episodes, key=lambda x: x['date'])

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    total_episodes = len(sorted_episodes)
    print(f"Found {total_episodes} episodes for '{parsed_feed.feed.get('title', 'Unknown Podcast')}'. Starting download (oldest first)...")

    newly_downloaded_count = 0
    already_existed_count = 0
    failed_count = 0
    
    # Thread-safe counters
    counter_lock = threading.Lock()
    
    def process_episode(episode_info):
        i, episode_data = episode_info
        nonlocal newly_downloaded_count, already_existed_count, failed_count
        entry = episode_data['entry']
        episode_title = entry.get("title", f"Untitled Episode {i+1}")

        # Construct a date prefix for filenames (YYYY-MM-DD)
        date_str = episode_data['date'].strftime('%Y-%m-%d') if episode_data['date'] != datetime.min else "nodate"
        prefixed_episode_title = f"{date_str} - {episode_title}"


        enclosures = entry.get("enclosures", [])
        if not enclosures:
            # Sometimes link is directly in 'link' if no enclosures
            if 'link' in entry and entry.link.endswith(('.mp3', '.m4a', '.ogg', '.wav', '.aac')): # Basic check
                episode_url = entry.link
            else:
                with counter_lock:
                    failed_count += 1
                return
        else:
            episode_url = None
            for enclosure in enclosures:
                if enclosure.get("type", "").startswith("audio"):
                    episode_url = enclosure.get("href")
                    break
            if not episode_url:
                episode_url = enclosures[0].get("href") # Fallback to first enclosure

        if not episode_url:
            with counter_lock:
                failed_count += 1
            return

        success, downloaded_filename, skipped_due_to_existence = download_episode(episode_url, output_dir, prefixed_episode_title)
        
        # Save metadata alongside the episode (whether new download or existing)
        if success:
            save_episode_metadata(entry, output_dir, prefixed_episode_title, episode_data['date'])

        with counter_lock:
            if success:
                if skipped_due_to_existence:
                    already_existed_count += 1
                else:
                    newly_downloaded_count += 1
            else:
                failed_count += 1
    
    # Process episodes with ThreadPoolExecutor
    episode_list = list(enumerate(sorted_episodes))
    
    if max_concurrent == 1:
        # Sequential processing (original behavior)
        for episode_info in episode_list:
            process_episode(episode_info)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = [executor.submit(process_episode, episode_info) for episode_info in episode_list]
            
            # Wait for all downloads to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    with counter_lock:
                        failed_count += 1


    print("\n--- Download Summary ---")
    print(f"Podcast: {parsed_feed.feed.get('title', 'Unknown Podcast')}")
    print(f"Output Directory: {os.path.abspath(output_dir)}")
    print(f"Total episodes in feed: {total_episodes}")
    print(f"Successfully downloaded (new): {newly_downloaded_count}")
    print(f"Already existed & complete (skipped): {already_existed_count}")
    print(f"Failed/Skipped (no link/error): {failed_count}")
    print("------------------------")


def main():
    """Main entry point for the podcastdl CLI."""
    parser = argparse.ArgumentParser(description="Download podcast episodes from a feed URL, oldest first.")
    parser.add_argument("feed_url", help="The URL of the podcast RSS feed.")
    parser.add_argument("-o", "--output", dest="output_dir", default="podcast_episodes",
                        help="The directory to save episodes (default: ./podcast_episodes or ./podcast_episodes/PodcastTitle).")
    parser.add_argument("-c", "--concurrent", dest="max_concurrent", type=int, default=3,
                        help="Maximum number of concurrent downloads (default: 3, use 1 for sequential).")

    args = parser.parse_args()

    if args.max_concurrent < 1:
        print("Error: --concurrent must be at least 1")
        return 1

    download_podcast_episodes(args.feed_url, args.output_dir, args.max_concurrent)

if __name__ == "__main__":
    main()
