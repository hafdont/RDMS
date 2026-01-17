from flask_socketio import SocketIO, emit, join_room
from flask import current_app, session
import os
from flask_login import current_user
from app.models import User, Task, DecisionEnum, Notification
from app.utils.db import db
import logging

logger = logging.getLogger(__name__)

socketio = SocketIO(cors_allowed_origins="*",
                    logger=False, 
                    async_mode="threading",
                    engineio_logger=False)  

def init_notifications(app):
    socketio.init_app(app)

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        emit('error', {'reason': 'unauthorized'})
        return False

    user_id = current_user.get_id()
    join_room(f"user_{user_id}")
    emit('connected', {'status': 'connected'})


def create_and_emit_notification(user_id, message, url=None, actor_id=None):
    notification = Notification(
        user_id=user_id, 
        message=message, 
        url=url, 
        actor_id=actor_id
    )
    db.session.add(notification)
    db.session.commit()

    # Emit via socket
    socketio.emit('new_notification', {
        'message': message,
        'url': url,
        'created_at': notification.created_at.isoformat() + 'Z'
    }, room=f"user_{user_id}")
