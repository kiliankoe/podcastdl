# podcastdl

A command-line tool to download podcast episodes from an RSS feed.

## Usage

To download a podcast, run the following command:

```bash
podcastdl <FEED_URL>
```

This will download all episodes from the given RSS feed into a directory named `podcast_episodes/<PodcastTitle>` in your current working directory, starting with the oldest episode.

You can specify a custom output directory using the `-o` or `--output` flag:

```bash
podcastdl <FEED_URL> -o /path/to/your/directory
```

The script will:
- Fetch and parse the RSS feed.
- Download episodes, oldest first.
- Sanitize episode titles for safe filenames.
- Create a date prefix (YYYY-MM-DD) for filenames.
- Skip episodes that already exist and appear complete.
- Provide a summary of downloaded, skipped, and failed episodes.
