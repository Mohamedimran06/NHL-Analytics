
import os

import streamlit as st
from streamlit_option_menu import option_menu
import pandas as pd
import pymysql
import requests

DB_CONFIG = {
    "host": st.secrets.get("DB_HOST", os.getenv("DB_HOST", "localhost")),
    "user": st.secrets.get("DB_USER", os.getenv("DB_USER", "root")),
    "password": st.secrets.get("DB_PASSWORD", os.getenv("DB_PASSWORD", "root")),
    "database": st.secrets.get("DB_NAME", os.getenv("DB_NAME", "nhl")),
    "port": int(st.secrets.get("DB_PORT", os.getenv("DB_PORT", "3306"))),
}


def localized_value(value):
    return value.get("default", "") if isinstance(value, dict) else value


def get_connection():
    return pymysql.connect(**DB_CONFIG)

def run_query(query, params=None):
    conn = get_connection()
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

@st.cache_data(ttl=3600)
def get_roster_names(team_abbrev):
    response = requests.get(
        f"https://api-web.nhle.com/v1/roster/{team_abbrev}/current",
        timeout=10,
    )
    response.raise_for_status()
    roster = response.json()
    players = {}

    for position in ("forwards", "defensemen", "goalies"):
        for player in roster.get(position, []):
            players[player["id"]] = {
                "first_name": localized_value(player.get("firstName", {})),
                "last_name": localized_value(player.get("lastName", {})),
                "headshot": player.get("headshot"),
            }
    return players


@st.cache_data(ttl=3600)
def get_all_players(team_abbrevs):
    players = []
    for team_abbrev in team_abbrevs:
        try:
            roster = get_roster_names(team_abbrev)
        except requests.RequestException:
            continue
        for player_id, name in roster.items():
            players.append({
                "player_id": player_id,
                "first_name": name["first_name"],
                "last_name": name["last_name"],
                "headshot": name["headshot"],
                "team_abbrev": team_abbrev,
            })

    return pd.DataFrame(players).drop_duplicates("player_id")

@st.cache_data(ttl=3600)
def get_standings_form():
    response = requests.get(
        "https://api-web.nhle.com/v1/standings/now",
        timeout=10,
    )
    response.raise_for_status()
    form = {}
    for team in response.json().get("standings", []):
        abbreviation = team.get("teamAbbrev", {})
        if isinstance(abbreviation, dict):
            abbreviation = abbreviation.get("default", "")
        wins = team.get("last5Wins")
        losses = team.get("last5Losses")
        form[abbreviation] = (
            f"{wins}-{losses}" if wins is not None and losses is not None else "N/A"
        )
    return form


with st.sidebar:
    st.image("assets/nhl_logo.svg", width=110)
    selected = option_menu(
        "NHL Analytics",
        ["Home", "Standings", "Team Info", "Player Search", "Leaderboards", "SQL Query"],
        icons=["house", "list", "info-circle", "search", "trophy", "code"],
        menu_icon="hockey-puck",
        default_index=0,
    )


if selected == "Home":
    st.title("🏒 National Hockey League")
    total_teams = run_query("SELECT COUNT(*) as count FROM teams")["count"][0]
    total_players = run_query(
        "SELECT COUNT(*) as count FROM ("
        "SELECT player_id FROM skater_season "
        "UNION SELECT player_id FROM goalie_season_stats"
        ") AS players"
    )["count"][0]
    total_games = run_query(
        "SELECT COUNT(DISTINCT game_id) as count FROM game_stats"
    )["count"][0]
    total_goals = run_query(
        "SELECT SUM(goals_for) as total FROM standings"
    )["total"][0]

    metrics = st.columns(4)
    metric_values = [
        ("Teams", total_teams),
        ("Players", total_players),
        ("Games", total_games),
        ("Goals", total_goals),
    ]
    for metric_column, (label, value) in zip(metrics, metric_values):
        with metric_column:
            with st.container(border=True):
                st.metric(label, value)

    st.subheader("Featured Teams")
    featured_teams = run_query(
        "SELECT team_name, logo_url FROM teams "
        "WHERE logo_url IS NOT NULL ORDER BY team_id LIMIT 6"
    )
    if not featured_teams.empty:
        team_columns = st.columns(len(featured_teams))
        for team_column, (_, team_row) in zip(team_columns, featured_teams.iterrows()):
            with team_column:
                st.image(team_row["logo_url"], use_container_width=True)
                st.caption(team_row["team_name"])

    # Optional: add charts
    # st.bar_chart(run_query("SELECT team_name, points FROM standings"))

elif selected == "Standings":
    st.title("📊 League Standings")
    st.subheader("Season: 2025-2026")
    df = run_query(
        "SELECT RANK() OVER (ORDER BY s.points DESC, s.wins DESC) AS team_position, "
        "t.logo_url, t.team_name, s.games_played, s.wins, s.losses, "
        "s.ot_losses, s.points, s.goals_for AS goals "
        "FROM standings s "
        "JOIN teams t ON s.team_id = t.team_id "
        "JOIN ("
        "SELECT team_id, season, MAX(standing_id) AS standing_id "
        "FROM standings GROUP BY team_id, season"
        ") latest ON s.standing_id = latest.standing_id "
        "WHERE s.season = '20252026' "
        "ORDER BY team_position"
    )
    st.dataframe(
        df,
        column_config={
            "logo_url": st.column_config.ImageColumn("Team Logo"),
        },
        hide_index=True,
        use_container_width=True,
    )

elif selected == "Team Info":
    st.title("🏟️ Team Information")
    teams = run_query("SELECT team_name, team_abbrev, logo_url FROM teams")
    team = st.selectbox("Select Team", teams["team_name"])
    selected_team = teams[teams["team_name"] == team].iloc[0]
    team_abbrev = selected_team["team_abbrev"]
    df = run_query(
        "SELECT * FROM skater_season WHERE team_id = "
        "(SELECT team_id FROM teams WHERE team_name = %s)",
        (team,),
    )

    team_profile, team_stats = st.columns([1, 3])
    with team_profile:
        if selected_team["logo_url"]:
            st.image(selected_team["logo_url"], use_container_width=True)
        st.caption("Built for the ice. Together.")
    with team_stats:
        st.subheader(f"{team} Players")
    try:
        roster_names = get_roster_names(team_abbrev)
        df.insert(2, "first_name", df["player_id"].map(
            lambda player_id: roster_names.get(player_id, {}).get("first_name", "")
        ))
        df.insert(3, "last_name", df["player_id"].map(
            lambda player_id: roster_names.get(player_id, {}).get("last_name", "")
        ))
    except requests.RequestException as error:
        st.warning(f"Could not load player names: {error}")
    if {"first_name", "last_name"}.issubset(df.columns):
        df = df[
            df["first_name"].notna()
            & df["last_name"].notna()
            & df["first_name"].ne("")
            & df["last_name"].ne("")
        ]
    df = df.drop(
        columns=["season", "player_id", "team_id", "stat_id", "avg_toi"],
        errors="ignore",
    )
    with team_stats:
        st.dataframe(df, hide_index=True, use_container_width=True)

elif selected == "Player Search":
    st.title("🔍 Player Search")
    teams = run_query("SELECT team_abbrev FROM teams")
    players = get_all_players(tuple(teams["team_abbrev"]))
    if not players.empty:
        players["full_name"] = (
            players["first_name"] + " " + players["last_name"]
        )
        players = players.drop_duplicates("player_id").sort_values("full_name")
        selected_player = st.selectbox(
            "Search player",
            players["full_name"].tolist(),
        )
        matches = players[players["full_name"] == selected_player]
        for _, player_profile in matches.iterrows():
            player_id = int(player_profile["player_id"])
            skater_stats = run_query(
                "SELECT * FROM skater_season WHERE player_id = %s",
                (player_id,),
            )
            goalie_stats = run_query(
                "SELECT * FROM goalie_season_stats WHERE player_id = %s",
                (player_id,),
            )
            if not skater_stats.empty:
                skater_stats.insert(1, "player_name", selected_player)
                skater_stats = skater_stats.drop(columns=["player_id"])
            if not goalie_stats.empty:
                goalie_stats.insert(1, "player_name", selected_player)
                goalie_stats = goalie_stats.drop(columns=["player_id"])

            with st.container(border=True):
                profile_image, profile_details = st.columns([1, 2])
                with profile_image:
                    if player_profile["headshot"]:
                        st.image(player_profile["headshot"], width=180)
                with profile_details:
                    st.header(selected_player)
                    st.caption(f"Team: {player_profile['team_abbrev']}")

                if not skater_stats.empty:
                    latest_skater = skater_stats.iloc[-1]
                    st.subheader("Skater season overview")
                    metrics = st.columns(4)
                    metrics[0].metric("Games", int(latest_skater["games_played"]))
                    metrics[1].metric("Goals", int(latest_skater["goals"]))
                    metrics[2].metric("Assists", int(latest_skater["assists"]))
                    metrics[3].metric("Points", int(latest_skater["points"]))
                    with st.expander("View full skater statistics"):
                        st.dataframe(skater_stats, use_container_width=True)
                if not goalie_stats.empty:
                    latest_goalie = goalie_stats.iloc[-1]
                    st.subheader("Goalie season overview")
                    metrics = st.columns(4)
                    metrics[0].metric("Games", int(latest_goalie["games_played"]))
                    metrics[1].metric("Wins", int(latest_goalie["wins"]))
                    metrics[2].metric("Save %", f"{latest_goalie['save_pct']:.3f}")
                    metrics[3].metric("Shutouts", int(latest_goalie["shutouts"]))
                    with st.expander("View full goalie statistics"):
                        st.dataframe(goalie_stats, use_container_width=True)

elif selected == "Leaderboards":
    st.title("🏆 Leaderboards")
    teams = run_query("SELECT team_abbrev FROM teams")
    players = get_all_players(tuple(teams["team_abbrev"]))
    if not players.empty:
        players["player_name"] = (
            players["first_name"] + " " + players["last_name"]
        )
        player_names = dict(zip(players["player_id"], players["player_name"]))
    else:
        player_names = {}

    st.subheader("Top Goal Scorers")
    top_scorers = run_query("""
        SELECT player_id AS player, SUM(goals) AS total_goals
        FROM skater_season
        GROUP BY player_id
        ORDER BY total_goals DESC
        LIMIT 5
    """)
    top_scorers["player"] = top_scorers["player"].map(
        lambda player_id: player_names.get(player_id, "Unknown player")
    )
    top_scorers.insert(0, "Rank", range(1, len(top_scorers) + 1))
    st.dataframe(top_scorers, hide_index=True, use_container_width=True)

    st.subheader("Most Assists")
    most_assists = run_query("""
        SELECT player_id AS player, SUM(assists) AS total_assists
        FROM skater_season
        GROUP BY player_id
        ORDER BY total_assists DESC
        LIMIT 5
    """)
    most_assists["player"] = most_assists["player"].map(
        lambda player_id: player_names.get(player_id, "Unknown player")
    )
    most_assists.insert(0, "Rank", range(1, len(most_assists) + 1))
    st.dataframe(most_assists, hide_index=True, use_container_width=True)

    st.subheader("Most Hat Tricks")
    most_hattricks = run_query("""
        SELECT player_id AS player, COUNT(*) AS total_hattricks
        FROM (
            SELECT player_id, game_id
            FROM game_stats
            GROUP BY player_id, game_id
            HAVING SUM(goals) >= 3
        ) AS hat_trick_games
        GROUP BY player_id
        ORDER BY total_hattricks DESC
        LIMIT 5
    """)
    most_hattricks["player"] = most_hattricks["player"].map(
        lambda player_id: player_names.get(player_id, "Unknown player")
    )
    most_hattricks.insert(0, "Rank", range(1, len(most_hattricks) + 1))
    st.dataframe(most_hattricks, hide_index=True, use_container_width=True)

    st.subheader("Best Goalies (Save %)")
    best_goalies = run_query("""
        SELECT g.player_id AS goalie, MAX(g.save_pct) AS save_pct
        FROM goalie_season_stats g
        GROUP BY g.player_id
        ORDER BY save_pct DESC
        LIMIT 5
    """)
    best_goalies["goalie"] = best_goalies["goalie"].map(
        lambda player_id: player_names.get(player_id, "Unknown player")
    )
    best_goalies.insert(0, "Rank", range(1, len(best_goalies) + 1))
    st.dataframe(best_goalies, hide_index=True, use_container_width=True)

elif selected == "SQL Query":
    st.title("💻 Run Custom SQL")

    sql_questions = {
        "Custom SQL": "",
        "1. Which team has scored the most total goals this season?": """
            SELECT t.team_name, SUM(s.goals_for) AS total_goals
            FROM standings s
            JOIN teams t ON s.team_id = t.team_id
            WHERE s.season = '20252026'
            GROUP BY t.team_name
            ORDER BY total_goals DESC
            LIMIT 1
        """,
        "2. Who are the top 5 point scorers across the entire league?": """
            SELECT player_id, SUM(points) AS total_points
            FROM skater_season
            GROUP BY player_id
            ORDER BY total_points DESC
            LIMIT 5
        """,
        "3. Which players have scored more than 20 goals and recorded more than 30 assists in the season?": """
            SELECT player_id, SUM(goals) AS total_goals, SUM(assists) AS total_assists
            FROM skater_season
            GROUP BY player_id
            HAVING SUM(goals) > 20 AND SUM(assists) > 30
            ORDER BY total_goals DESC, total_assists DESC
        """,
        "4. Which teams have a season points total above the league average?": """
            SELECT t.team_name, s.points
            FROM standings s
            JOIN teams t ON s.team_id = t.team_id
            WHERE s.season = '20252026'
            AND s.points > (
                SELECT AVG(points)
                FROM standings
                WHERE season = '20252026'
            )
            ORDER BY s.points DESC
        """,
        "5. Which divisions have an average team points total above 90?": """
            SELECT t.division_name, AVG(s.points) AS avg_team_points
            FROM standings s
            JOIN teams t ON s.team_id = t.team_id
            WHERE s.season = '20252026'
            GROUP BY t.division_name
            HAVING AVG(s.points) > 90
            ORDER BY avg_team_points DESC
        """,
        "6. What is the average number of wins, losses, and points by conference?": """
            SELECT t.conference_name,
                   AVG(s.wins) AS average_wins,
                   AVG(s.losses) AS average_losses,
                   AVG(s.points) AS average_points
            FROM standings s
            JOIN teams t ON s.team_id = t.team_id
            WHERE s.season = '20252026'
            GROUP BY t.conference_name
            ORDER BY average_points DESC
        """,
        "7. Which teams have scored more goals than the league average?": """
            SELECT t.team_name, s.goals_for
            FROM standings s
            JOIN teams t ON s.team_id = t.team_id
            WHERE s.season = '20252026'
              AND s.goals_for > (
                  SELECT AVG(goals_for)
                  FROM standings
                  WHERE season = '20252026'
              )
            ORDER BY s.goals_for DESC
        """,
        "8. How many players are listed for each team?": """
            SELECT t.team_name, COUNT(p.player_id) AS player_count
            FROM teams t
            LEFT JOIN player p ON p.team_id = t.team_id
            GROUP BY t.team_id, t.team_name
            ORDER BY player_count DESC, t.team_name
        """,
        "9. Which teams have at least 10 listed players?": """
            SELECT t.team_name, COUNT(p.player_id) AS player_count
            FROM teams t
            JOIN player p ON p.team_id = t.team_id
            GROUP BY t.team_id, t.team_name
            HAVING COUNT(p.player_id) >= 10
            ORDER BY player_count DESC
        """,
        "10. What are the top 10 players by total goals and assists?": """
            SELECT p.first_name, p.last_name,
                   SUM(s.goals) AS total_goals,
                   SUM(s.assists) AS total_assists,
                   SUM(s.points) AS total_points
            FROM player p
            JOIN skater_season s ON s.player_id = p.player_id
            GROUP BY p.player_id, p.first_name, p.last_name
            ORDER BY total_points DESC, total_goals DESC
            LIMIT 10
        """,
        "11. Which players have more goals than the average player total?": """
            SELECT p.first_name, p.last_name, SUM(s.goals) AS total_goals
            FROM player p
            JOIN skater_season s ON s.player_id = p.player_id
            GROUP BY p.player_id, p.first_name, p.last_name
            HAVING SUM(s.goals) > (
                SELECT AVG(player_goals)
                FROM (
                    SELECT SUM(goals) AS player_goals
                    FROM skater_season
                    GROUP BY player_id
                ) AS goal_totals
            )
            ORDER BY total_goals DESC
        """,
        "12. What is the average save percentage by goalie team?": """
            SELECT t.team_name, AVG(g.save_pct) AS average_save_pct,
                   COUNT(DISTINCT g.player_id) AS goalie_count
            FROM goalie_season_stats g
            JOIN player p ON p.player_id = g.player_id
            JOIN teams t ON t.team_id = p.team_id
            GROUP BY t.team_id, t.team_name
            HAVING COUNT(DISTINCT g.player_id) > 0
            ORDER BY average_save_pct DESC
        """,
        "13. Which players have recorded at least 3 points in a game?": """
            SELECT p.first_name, p.last_name,
                   gs.game_id, SUM(gs.points) AS game_points
            FROM game_stats gs
            JOIN player p ON p.player_id = gs.player_id
            GROUP BY p.player_id, p.first_name, p.last_name, gs.game_id
            HAVING SUM(gs.points) >= 3
            ORDER BY game_points DESC, gs.game_id
        """,
        "14. What is the total number of game-stat records by team?": """
            SELECT t.team_name, COUNT(gs.stat_id) AS stat_record_count,
                   SUM(gs.goals) AS total_goals,
                   SUM(gs.points) AS total_points
            FROM teams t
            JOIN player p ON p.team_id = t.team_id
            JOIN game_stats gs ON gs.player_id = p.player_id
            GROUP BY t.team_id, t.team_name
            ORDER BY total_points DESC, stat_record_count DESC
        """,
        "15. Which players have appeared in more than 10 game-stat records?": """
            SELECT p.first_name, p.last_name,
                   COUNT(gs.stat_id) AS games_recorded,
                   SUM(gs.points) AS total_points
            FROM player p
            JOIN game_stats gs ON gs.player_id = p.player_id
            GROUP BY p.player_id, p.first_name, p.last_name
            HAVING COUNT(gs.stat_id) > 10
            ORDER BY games_recorded DESC, total_points DESC
        """,
    }

    selected_question = st.selectbox("Select a SQL question", list(sql_questions.keys()))
    query = st.text_area("Enter SQL Query", value=sql_questions[selected_question], height=220)

    if st.button("Run"):
        try:
            df = run_query(query)
            st.dataframe(df)
        except Exception as e:
            st.error(f"Error: {e}")
