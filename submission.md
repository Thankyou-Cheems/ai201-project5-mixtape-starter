# Project 5 Submission - Mixtape Bug Hunt

## AI Usage

I used AI assistance only as an explanation and navigation aid. I did not use it as the author of the fixes, the final source of truth, or the tool that decided which bugs were solved. The actual project work I performed myself was: running the tests, reading the files, tracing the code paths, editing the service functions, adding regression tests, rerunning pytest, reviewing the diff, and creating the separate `fix:` commits.

Specific ways I used AI:

- Before changing code, I asked AI to explain the vocabulary and structure of the inherited Flask app: what a Blueprint route does, what a service-layer function is responsible for, how SQLAlchemy models are used by service code, what a pytest fixture/test failure is telling me, and how to follow a route -> service -> model call path. After that explanation, I manually read `app.py`, `routes/`, `services/`, `models.py`, and `tests/` and wrote the codebase map myself.
- For the listening streak bug, I first reproduced the failure in `tests/test_streaks.py::test_streak_increments_on_sunday`. I then traced the path from `routes/songs.py` to `services/streak_service.py::record_listening_event()` and `services/streak_service.py::update_listening_streak()`. I asked AI to clarify what Python's `datetime.weekday()` returns and how a Saturday-to-Sunday transition should be interpreted. I verified the explanation by reading the test dates and the condition in the service code, then I made the actual fix by removing the Sunday exclusion from the consecutive-day logic and reran the streak tests.
- For the playlist bug, I reproduced the missing final song with `tests/test_playlists.py`, especially the checks that expected five songs and expected `Track 5` at the end. I traced `routes/playlists.py` to `services/playlist_service.py::get_playlist_songs()` and inspected the `playlist_entries` join table in `models.py` to confirm that playlist order comes from `position`. I asked AI to explain the SQLAlchemy join/order-by pattern and the Python slice `songs[:-1]`. I verified in the actual code that the query was correct and the slice was dropping the last element, then I changed the return statement to include every song and reran the playlist tests.
- For the "Friends Listening Now" bug, I read the feed service and wrote a regression test in `tests/test_feed.py` that created one friend who listened today and one friend who listened just before the start of today. I used AI only to clarify the difference between a rolling 24-hour window and "today" as a calendar-day filter. I verified the required behavior in the test, changed `services/feed_service.py` so the cutoff starts at the beginning of the current day, and reran the feed test.
- For the rating notification bug, I read `services/notification_service.py::rate_song()`, `models.py`, and the `Song`, `Rating`, `User`, and `Notification` relationships. I asked AI to explain the intended data relationship: the rater creates or updates a `Rating`, but the original song sharer should receive a `Notification` only when another user rates their song. I then wrote `tests/test_notifications.py` to cover both cases: rating another user's song creates a `song_rated` notification, and rating your own song does not notify yourself. I made the service change, then reran the notification tests.
- After each fix, I verified the result myself by rerunning the relevant pytest file, checking the changed code, and recording the root cause analysis in `submission.md`. At the end, I reran the full pytest suite, reviewed `git diff`, and checked `git log --oneline` to confirm the branch had separate `fix:` commits for the bugs.

I also had to override or narrow AI output. When AI explanations were broad, such as "look through the services" or "check notification creation," I did not treat that as a diagnosis. I only acted on issues I could reproduce with a test or verify by reading the exact route, service, model, and test files. AI helped me understand terms and call-stack relationships; the reproduction, line-level diagnosis, edits, regression tests, and final verification were done by me.

## Codebase Map

Write this before starting bug fixes.

### Main Files And Roles

- `app.py`: creates the Flask app, initializes SQLAlchemy, loads environment-based config, registers the `songs`, `playlists`, `users`, and `feed` blueprints, and creates tables for the local SQLite database.
- `models.py`: defines the core database models: `User`, `Song`, `Tag`, `ListeningEvent`, `Rating`, `Playlist`, and `Notification`. It also defines join tables for friendships, song tags, and playlist entries. `playlist_entries` is not a plain many-to-many join: it stores `position`, `added_by`, and `added_at`, so playlist ordering must be read from that table.
- `routes/`: contains thin HTTP handlers. Routes parse request data, call service-layer functions, convert return values to JSON, and translate `ValueError` exceptions into client errors.
- `services/`: contains the business logic for streaks, playlists, search, feed data, and notifications. The README says the known bugs live here, and the routes mostly delegate directly into these functions.
- `tests/`: contains pytest regression coverage for streak behavior, playlist retrieval, and search behavior. The starter baseline exposed failures in the Sunday streak path and playlist song retrieval.

### Data Flow For One Feature

Feature traced: rating a song.

1. Request: `POST /songs/<song_id>/rate` with JSON containing `user_id` and `score`.
2. Route function: `routes/songs.py::rate()` validates the JSON fields and converts `score` to an integer.
3. Service function: `services/notification_service.py::rate_song()` validates the score, loads the `Song` and rater `User`, then creates or updates a `Rating`.
4. Model/data touched: `Song` identifies the original sharer, `User` identifies the rater, `Rating` stores the score, and `Notification` should be created when someone else rates the sharer's song.
5. Response: the route returns `rating.to_dict()` with HTTP 201, or a JSON error if validation fails.

### Patterns Noticed

- Routes stay small and service functions own the app behavior.
- Most service functions load models by ID, raise `ValueError` for missing records, and return model dictionaries or ORM instances.
- Several features depend on join-table metadata, especially playlist ordering, so using relationship lists alone can hide important columns.
- Time-based behavior is stored as `datetime` values in the models, so boundary bugs need explicit date/time comparisons.

## Bug Fix 1

### Issue Number And Title

Issue #1: My listening streak keeps resetting

### How You Reproduced It

I ran the starter pytest suite and reproduced the failure in `tests/test_streaks.py::test_streak_increments_on_sunday`. The test creates a user, calls `update_listening_streak()` for Saturday, then calls it again for Sunday. The expected streak is 2 because the dates are consecutive, but the starter code reset it to 1.

### How You Found The Root Cause

I traced the listening flow from `POST /songs/<song_id>/listen` in `routes/songs.py` to `record_listening_event()` and then `update_listening_streak()` in `services/streak_service.py`. The route and event creation were not involved in the failing unit test, so the root cause had to be in the date comparison inside `update_listening_streak()`. The suspicious condition was `days_since_last == 1 and today.weekday() != 6`.

### The Root Cause

The function already computed `days_since_last` correctly. A consecutive Saturday-to-Sunday listen has `days_since_last == 1`, but Python's `date.weekday()` returns `6` for Sunday. The extra `today.weekday() != 6` condition prevented Sunday from ever counting as a consecutive day, so Sunday listens reset the streak even when the user listened the previous day.

### Your Fix And Side-Effect Check

I removed the Sunday exclusion and let any `days_since_last == 1` increment the streak. I checked the existing streak tests because they cover new users, normal consecutive days, duplicate listens on the same day, skipped days, and the Saturday-to-Sunday boundary.

## Bug Fix 2

### Issue Number And Title

Issue #5: The last song in a playlist never shows up

### How You Reproduced It

I ran `tests/test_playlists.py`. The fixture builds a playlist with five songs at positions 1 through 5. `test_playlist_returns_all_songs` expected five results but got four, and `test_playlist_returns_songs_in_order` showed that `Track 5` was missing.

### How You Found The Root Cause

I traced `GET /playlists/<playlist_id>/songs` in `routes/playlists.py` to `services/playlist_service.py::get_playlist_songs()`. The SQL query joined `Song` through `playlist_entries`, filtered by `playlist_id`, and ordered by `playlist_entries.position`, which matched the data model. The bug appeared after the query, in the final list comprehension.

### The Root Cause

`get_playlist_songs()` returned `[song.to_dict() for song in songs[:-1]]`. The slice `songs[:-1]` intentionally excludes the last element of the list, so every non-empty playlist dropped its final song even though the database query returned it correctly.

### Your Fix And Side-Effect Check

I changed the return value to iterate over `songs` directly. I checked the playlist tests because they cover all songs, ordering by position, and the empty-playlist case. The empty list still returns `[]`, while populated playlists now include the final item.

## Bug Fix 3

### Issue Number And Title

Issue #2: Friends Listening Now shows people from yesterday

### How You Reproduced It

The starter did not include a test for this issue, so I added a focused regression test. The test creates a user with two friends: one friend listened five minutes ago today, and another listened five minutes before today's UTC midnight. The yesterday listen is still within a rolling 24-hour window, so the starter logic would include it even though it happened yesterday.

### How You Found The Root Cause

I traced `GET /feed/<user_id>/listening-now` in `routes/feed.py` to `services/feed_service.py::get_friends_listening_now()`. The function loads the user's friends, queries `ListeningEvent` rows after a cutoff, orders by `listened_at`, and deduplicates to the most recent song per friend. The dedupe was not the issue; the cutoff was.

### The Root Cause

The service used `datetime.now(timezone.utc) - timedelta(hours=24)` as the cutoff. That defines "now" as a rolling 24-hour window, so a listen from yesterday evening or just before midnight still appears the next day. The issue title expects "Friends Listening Now" to be scoped to today's listening activity, not every event from the last 24 hours.

### Your Fix And Side-Effect Check

I changed the cutoff to the start of the current UTC day by replacing hour, minute, second, and microsecond with zero. I added `tests/test_feed.py::test_listening_now_excludes_yesterday_even_within_24_hours` to verify that today's friend appears while yesterday's recent friend is excluded. I also checked that the existing friend dedupe and ordering code stayed unchanged.

## Bug Fix 4

### Issue Number And Title

Issue #4: I got notified when a friend added my song to a playlist but not when they rated it

### How You Reproduced It

The starter did not include a notification test for ratings, so I added one. The reproduction creates a sharer, a different rater, and a song owned by the sharer. Calling `rate_song(rater.id, song.id, 5)` created a `Rating` but no `Notification` for the sharer in the starter logic.

### How You Found The Root Cause

I traced `POST /songs/<song_id>/rate` in `routes/songs.py` to `services/notification_service.py::rate_song()`. Then I compared it with `add_to_playlist()` in the same service because playlist notifications were the working behavior described by the issue. `add_to_playlist()` validates the actor and song, performs the action, and then calls `create_notification()` for the original sharer when the actor is someone else. `rate_song()` stopped after committing the rating.

### The Root Cause

The rating path had the model update but not the notification side effect. It created or updated the `Rating` row and committed, but it never checked whether the rated song belonged to another user and never created a `song_rated` notification. The missing behavior was architectural: the route used the right service, but the service did not mirror the notification pattern used by playlist additions.

### Your Fix And Side-Effect Check

I added a notification after a successful rating commit when `song.shared_by != user_id`. The notification type is `song_rated`, and the body includes the rater username, song title, and score. I added tests for both sides of the condition: a friend's rating notifies the original sharer, while rating your own song does not create a self-notification.
