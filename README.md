# podcastdl

A command-line tool to download podcast episodes from an RSS feed.

## Usage

To download a podcast, run the following command:

```bash
podcastdl <FEED_URL>
```

This will download all episodes from the given RSS feed into a directory named `podcast_episodes/<PodcastTitle>` in your current working directory, starting with the oldest episode.

### Options

```bash
podcastdl <FEED_URL> -o /path/to/your/directory    # Custom output directory
podcastdl <FEED_URL> -c 5                          # 5 concurrent downloads (default: 3)
```

The script will:
- Fetch and parse the RSS feed.
- Download episodes with configurable parallelism (default: 3 concurrent).
- Create date-prefixed filenames (YYYY-MM-DD - Episode Title.ext).
- Save episode metadata as companion .txt files with descriptions and show notes.
- Skip episodes that already exist and appear complete.
- Provide a summary of downloaded, skipped, and failed episodes.
