document.addEventListener('DOMContentLoaded', () => {
    const nameForm = document.getElementById('name-form');
    const nameInput = document.getElementById('name-input');
    const joinForm = document.getElementById('join-form');
    const createGameBtn = document.getElementById('create-game-btn');
    const joinFormBtn = document.getElementById('join-form-btn');

    // Function to handle the "Join Karein" button click
    window.showJoinInput = () => {
        // First, check if a name has been entered
        const username = nameInput.value.trim();
        if (!username) {
            alert('Pehle apna naam daalo!');
            nameInput.focus();
            return;
        }
        
        // Hide the initial buttons and show the join form
        nameForm.querySelector('.button-group').style.display = 'none';
        joinForm.style.display = 'block';
    };

    // Event listener for creating a game
    createGameBtn.addEventListener('click', async (e) => {
        e.preventDefault(); // Prevent the form's default submission
        const username = nameInput.value.trim();
        if (username) {
            sessionStorage.setItem('username', username);

            try {
                // Make a POST request to the create_game endpoint
                const response = await fetch('/create_game', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                const data = await response.json();
                
                if (response.ok) {
                    // Redirect to the new lobby with the room code
                    window.location.href = `${data.link}?username=${username}`;
                } else {
                    console.error('Failed to create game:', data);
                    alert('Game Banane mein dikkat ho gayi. Try again!');
                }
            } catch (error) {
                console.error('Network or server error:', error);
                alert('Server se connect nahi ho paya. Check your connection!');
            }
        }
    });

    // Event listener for joining a game
    joinForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const roomCode = document.getElementById('room-code-input').value.trim().toUpperCase();
        const username = nameInput.value.trim(); // Get the username from the initial input
        
        if (roomCode && username) {
            window.location.href = `/lobby/${roomCode}?username=${username}`;
        } else {
            alert('Pehle apna naam aur Room Code daalo!');
        }
    });
});