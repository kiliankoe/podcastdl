import feedparser
import requests
import os
import re
from datetime import datetime
from tqdm import tqdm
import argparse

def sanitize_filename(filename):
    """Removes invalid characters from a filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

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
                print(f"'{filename}' already exists and seems complete. Skipping.")
                return True, filename, True # Added flag for skipped
            else:
                print(f"'{filename}' already exists but might be incomplete or size unknown. Re-downloading.")
        else:
            print(f"Downloading: '{filename}'")

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

def download_podcast_episodes(feed_url, output_dir="podcast_episodes"):
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
        print(f"Created output directory: {output_dir}")

    total_episodes = len(sorted_episodes)
    print(f"Found {total_episodes} episodes for '{parsed_feed.feed.get('title', 'Unknown Podcast')}'. Starting download (oldest first)...")

    newly_downloaded_count = 0
    already_existed_count = 0
    failed_count = 0

    for i, episode_data in enumerate(sorted_episodes):
        entry = episode_data['entry']
        episode_title = entry.get("title", f"Untitled Episode {i+1}")

        # Construct a date prefix for filenames (YYYY-MM-DD)
        date_str = episode_data['date'].strftime('%Y-%m-%d') if episode_data['date'] != datetime.min else "nodate"
        prefixed_episode_title = f"{date_str} - {episode_title}"

        print(f"\nProcessing episode {i+1}/{total_episodes}: '{episode_title}' (Published: {date_str})")

        enclosures = entry.get("enclosures", [])
        if not enclosures:
            # Sometimes link is directly in 'link' if no enclosures
            if 'link' in entry and entry.link.endswith(('.mp3', '.m4a', '.ogg', '.wav', '.aac')): # Basic check
                episode_url = entry.link
            else:
                print(f"No download link (enclosure or suitable link) found for '{episode_title}'. Skipping.")
                failed_count += 1 # Or a specific "skipped_no_link" counter
                continue
        else:
            episode_url = None
            for enclosure in enclosures:
                if enclosure.get("type", "").startswith("audio"):
                    episode_url = enclosure.get("href")
                    break
            if not episode_url:
                episode_url = enclosures[0].get("href") # Fallback to first enclosure

        if not episode_url:
            print(f"Could not determine download URL for '{episode_title}'. Skipping.")
            failed_count +=1
            continue

        success, downloaded_filename, skipped_due_to_existence = download_episode(episode_url, output_dir, prefixed_episode_title)

        if success:
            if skipped_due_to_existence:
                already_existed_count += 1
            else:
                newly_downloaded_count += 1
        else:
            failed_count += 1
            print(f"Failed to download '{prefixed_episode_title}'.")


    print("\n--- Download Summary ---")
    print(f"Podcast: {parsed_feed.feed.get('title', 'Unknown Podcast')}")
    print(f"Output Directory: {os.path.abspath(output_dir)}")
    print(f"Total episodes in feed: {total_episodes}")
    print(f"Successfully downloaded (new): {newly_downloaded_count}")
    print(f"Already existed & complete (skipped): {already_existed_count}")
    print(f"Failed/Skipped (no link/error): {failed_count}")
    print("------------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download podcast episodes from a feed URL, oldest first.")
    parser.add_argument("feed_url", help="The URL of the podcast RSS feed.")
    parser.add_argument("-o", "--output", dest="output_dir", default="podcast_episodes",
                        help="The directory to save episodes (default: ./podcast_episodes or ./podcast_episodes/PodcastTitle).")

    args = parser.parse_args()

    download_podcast_episodes(args.feed_url, args.output_dir)
