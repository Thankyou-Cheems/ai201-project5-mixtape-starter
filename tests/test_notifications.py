"""
tests/test_notifications.py - Mixtape

Tests for notification creation.
"""

import pytest

from app import create_app, db
from models import Notification, Song, User
from services.notification_service import rate_song


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_rating_friend_song_notifies_original_sharer(app):
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        rater = User(username="rater", email="rater@example.com")
        db.session.add_all([sharer, rater])
        db.session.flush()

        song = Song(title="Shared Track", artist="Mixtape", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        rate_song(rater.id, song.id, 5)

        notification = db.session.query(Notification).filter_by(user_id=sharer.id).one()
        assert notification.notification_type == "song_rated"
        assert "rater rated your song 'Shared Track' 5/5." == notification.body


def test_rating_own_song_does_not_notify_self(app):
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        db.session.add(sharer)
        db.session.flush()

        song = Song(title="Own Track", artist="Mixtape", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        rate_song(sharer.id, song.id, 4)

        notifications = db.session.query(Notification).filter_by(user_id=sharer.id).all()
        assert notifications == []
