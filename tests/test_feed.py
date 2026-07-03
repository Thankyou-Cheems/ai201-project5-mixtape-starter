"""
tests/test_feed.py - Mixtape

Tests for friends listening now feed logic.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import create_app, db
from models import ListeningEvent, Song, User
from services.feed_service import get_friends_listening_now


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_listening_now_excludes_yesterday_even_within_24_hours(app):
    """
    Friends Listening Now should show today's listens, not a rolling 24-hour window.
    """
    with app.app_context():
        listener = User(username="listener", email="listener@example.com")
        today_friend = User(username="today_friend", email="today@example.com")
        yesterday_friend = User(username="yesterday_friend", email="yesterday@example.com")
        db.session.add_all([listener, today_friend, yesterday_friend])
        db.session.flush()

        listener.friends.append(today_friend)
        listener.friends.append(yesterday_friend)

        song = Song(title="Now Playing", artist="Mixtape", shared_by=listener.id)
        db.session.add(song)
        db.session.flush()

        now = datetime.now(timezone.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_listen = now - timedelta(minutes=5)
        yesterday_listen = start_of_today - timedelta(minutes=5)

        db.session.add_all([
            ListeningEvent(user_id=today_friend.id, song_id=song.id, listened_at=today_listen),
            ListeningEvent(user_id=yesterday_friend.id, song_id=song.id, listened_at=yesterday_listen),
        ])
        db.session.commit()

        feed = get_friends_listening_now(listener.id)
        usernames = [entry["friend"]["username"] for entry in feed]

        assert usernames == ["today_friend"]
