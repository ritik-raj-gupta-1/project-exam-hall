import os
import random
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_socketio import SocketIO, join_room, emit
from dotenv import load_dotenv
from database import get_db_connection, put_db_connection
import uuid

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SUPABASE_KEY")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Global state for active games
# This should ideally be stored in a a cache like Redis for production,
# but for a simple game, in-memory is a good start.
game_rooms = {}

ROLES = ['VC', 'Professor', 'Invigilator', 'Cheater', 'Student', 'Student']

# --- Game Logic Functions ---
def assign_roles(room_code):
    if room_code not in game_rooms or len(game_rooms[room_code]['players']) < 3:
        return {"status": "error", "message": "Not enough players."}

    players = list(game_rooms[room_code]['players'].keys())
    shuffled_roles = random.sample(ROLES, len(players))

    for player_name, role in zip(players, shuffled_roles):
        game_rooms[room_code]['players'][player_name]['role'] = role
        sid = game_rooms[room_code]['players'][player_name]['sid']
        emit('role_reveal', {'role': role}, room=sid)

    game_rooms[room_code]['state'] = 'in_progress'
    socketio.emit('game_start', {'message': 'Game Shuru Karein!'}, room=room_code)
    
    # Start the timer
    socketio.start_background_task(target=game_timer, room_code=room_code, duration=90)
    
    return {"status": "success"}

def game_timer(room_code, duration):
    import time
    for i in range(duration, 0, -1):
        if game_rooms.get(room_code, {}).get('state') != 'in_progress':
            break  # Game ended prematurely
        socketio.emit('timer_update', {'time_left': i}, room=room_code)
        time.sleep(1)
    else:
        # If loop completes, time is up
        socketio.emit('game_over', {'result': 'Cheater bach nikla!'}, room=room_code)
        # Store result in DB
        log_game_result(room_code, 'Cheater', 'escaped')
        game_rooms[room_code]['state'] = 'finished'


def log_game_result(room_code, winner_role, result_type):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # This is a simplified logging function.
        # A professional system would have more detailed player stats.
        query = """
        INSERT INTO game_results (room_code, winner_role, result_type)
        VALUES (%s, %s, %s);
        """
        cursor.execute(query, (room_code, winner_role, result_type))
        conn.commit()
        print(f"Game result logged for room {room_code}.")
    except Exception as e:
        print(f"Error logging game result: {e}")
    finally:
        if conn:
            put_db_connection(conn)


# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_game', methods=['POST'])
def create_game():
    room_code = str(uuid.uuid4())[:6].upper()
    game_rooms[room_code] = {
        'players': {},
        'state': 'lobby'
    }
    return jsonify({"room_code": room_code, "link": f"/lobby/{room_code}"})

@app.route('/lobby/<room_code>')
def lobby(room_code):
    if room_code not in game_rooms:
        return redirect(url_for('index'))
    return render_template('lobby.html', room_code=room_code)

# --- WebSocket Events ---
@socketio.on('connect')
def handle_connect():
    print(f"Client connected with SID: {request.sid}")

@socketio.on('join_game')
def handle_join_game(data):
    username = data.get('username')
    room_code = data.get('room_code')
    sid = request.sid

    if not username or not room_code or room_code not in game_rooms:
        return
    
    # Store player data
    game_rooms[room_code]['players'][username] = {'sid': sid, 'role': None, 'ready': False}
    join_room(room_code)
    
    # Send updated player list to all clients in the room
    player_list = list(game_rooms[room_code]['players'].keys())
    emit('update_players', {'players': player_list}, room=room_code)
    emit('message', {'msg': f'{username} has joined.'}, room=room_code)

@socketio.on('set_ready')
def handle_set_ready(data):
    username = data.get('username')
    room_code = data.get('room_code')
    
    if username in game_rooms[room_code]['players']:
        game_rooms[room_code]['players'][username]['ready'] = True
        
    ready_players = sum(1 for p in game_rooms[room_code]['players'].values() if p['ready'])
    total_players = len(game_rooms[room_code]['players'])
    
    emit('ready_status', {'ready': ready_players, 'total': total_players}, room=room_code)
    
    # Host is the first player, check if all are ready
    if total_players >= 3 and ready_players == total_players:
        emit('enable_start_button', room=game_rooms[room_code]['players'][list(game_rooms[room_code]['players'].keys())[0]]['sid'])

@socketio.on('start_game_request')
def handle_start_game_request(data):
    room_code = data.get('room_code')
    assign_roles(room_code)

@socketio.on('make_guess')
def handle_make_guess(data):
    guesser = data.get('guesser')
    target = data.get('target')
    room_code = data.get('room_code')

    if room_code not in game_rooms or game_rooms[room_code]['state'] != 'in_progress':
        return

    target_role = game_rooms[room_code]['players'][target]['role']
    
    if target_role == 'Cheater':
        emit('game_over', {'result': f'Pakda Gaya! {target} hi asli Cheater tha!'}, room=room_code)
        log_game_result(room_code, 'Invigilator', 'caught')
    else:
        emit('game_over', {'result': f'Arre Nahi! Invigilator ne ek masoom Student ko pakad liya.'}, room=room_code)
        log_game_result(room_code, 'Cheater', 'escaped_by_error')
    
    game_rooms[room_code]['state'] = 'finished'
    
@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    for room_code, room_data in list(game_rooms.items()):
        for player_name, player_data in list(room_data['players'].items()):
            if player_data['sid'] == sid:
                room_data['players'].pop(player_name)
                emit('message', {'msg': f'{player_name} has left.'}, room=room_code)
                player_list = list(room_data['players'].keys())
                emit('update_players', {'players': player_list}, room=room_code)
                print(f"Player {player_name} disconnected from room {room_code}.")
                return

if __name__ == '__main__':
    # Use gevent for production deployment
    socketio.run(app, host='0.0.0.0', port=os.environ.get('PORT', 5000), allow_unsafe_werkzeug=True)