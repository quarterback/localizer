# Localizer

Portland-area government RFP monitoring scraper. Monitors six procurement portals and surfaces new opportunities.

## Sources

| Source | Portal | Platform |
|--------|--------|----------|
| portland | City of Portland | SAP Ariba |
| multnomah | Multnomah County | JAGGAER |
| metro | Oregon Metro | Bid Locker |
| trimet | TriMet | JAGGAER |
| port | Port of Portland | PlanetBids |
| oregonbuys | State of Oregon | OregonBuys |

## Install

```bash
pip install -e .
```

## Usage

```bash
# Scrape all sources
localizer scrape

# Scrape specific sources
localizer scrape portland multnomah

# List open RFPs
localizer list

# Search by keyword
localizer search "technology"

# Show new RFPs from last 3 days
localizer new --days 3

# Generate digest of unnotified RFPs
localizer digest

# View scrape history
localizer history

# List available sources
localizer sources
```

## Data

RFPs are stored in SQLite at `~/.localizer/rfps.db`. Override with `--db /path/to/db`.
