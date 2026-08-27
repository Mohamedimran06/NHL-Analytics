# NHL Analytics Dashboard

This project is a Streamlit-based NHL analytics application that connects to a MySQL database and displays NHL team, player, standings, and leaderboard data.

## Features

- League standings dashboard
- Team information and player roster views
- Player search with season stats
- Leaderboard summaries
- Custom SQL query runner
- Predefined SQL questions in a dropdown

## Project Structure

```text
NHL/
├── app.py
├── README.md
├── assets/
│   └── nhl_logo.svg
├── data/
│   ├── game_stats.json
│   ├── goalie_season_stats.json
│   └── skater_season_stats.json
└── notebooks/
    ├── teams.ipynb
    ├── players.ipynb
    ├── games.ipynb
    ├── game_stats.ipynb
    ├── standings.ipynb
    ├── skater_season.ipynb
    └── goalie_season_stats.ipynb
```

- `app.py` – main Streamlit application
- `notebooks/` – data collection and database-loading notebooks
- `data/` – exported JSON data files
- `assets/` – application images and branding

## Requirements

Install the following Python packages:

```bash
pip install streamlit streamlit-option-menu pandas pymysql requests
```

## Run the App

From the project directory:

```bash
streamlit run app.py
```

Or using the project virtual environment:

```bash
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Database Setup

The app expects a MySQL database named `nhl` with the following main tables:

- `teams`
- `standings`
- `skater_season`
- `goalie_season_stats`
- `game_stats`
- `games`
- `player`


The connection is configured in `app.py` as:

```python
pymysql.connect(
    host="localhost",
    user="root",
    password="root",
    database="nhl",
)
```

## Notes

- The notebooks use live NHL API data and store selected data in MySQL.
- `players.ipynb` reads `team_id` and `team_abbrev` from `teams`, then calls:
    `https://api-web.nhle.com/v1/roster/{team_abbrev}/current`
- `games.ipynb` reads team abbreviations from `teams`, then calls:
    `https://api-web.nhle.com/v1/club-schedule-season/{team_abbrev}/20252026`
- The games notebook stores the fetched schedule in `schedule_df`.
- The player notebook stores the fetched roster data in `players_df` and loads it into `player`.
- Some dashboard queries rely on the season value `20252026`.
- Use the SQL Query page to run custom SQL or select a predefined question.

## Author

NHL Analytics Dashboard Project
