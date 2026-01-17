from app import create_app
from app.utils.notifications import socketio
import os
from dotenv import load_dotenv

load_dotenv()

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    is_debug = app.config.get('DEBUG', True)

    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=is_debug
    )
