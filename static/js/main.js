document.addEventListener('DOMContentLoaded', () => {
    const nameForm = document.getElementById('name-form');
    const joinForm = document.getElementById('join-form');
    const nameInput = document.getElementById('name-input');
    
    // Function to handle the "Join Karein" button click
    window.showJoinInput = () => {
        nameForm.querySelector('.button-group').style.display = 'none';
        joinForm.style.display = 'block';
    };

    // Event listener for the main form submission (Create or Join)
    nameForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const username = nameInput.value.trim();
        if (username) {
            // Store the username in session storage for later use in the lobby
            sessionStorage.setItem('username', username);
            
            if (e.submitter.textContent === 'Game Banayein') {
                // Submit to Flask route to create a game
                nameForm.submit();
            }
        }
    });

    // Event listener for the "Join" form submission
    joinForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const roomCode = document.getElementById('room-code-input').value.trim().toUpperCase();
        const username = sessionStorage.getItem('username');
        if (roomCode && username) {
            // Redirect to the lobby with the room code
            window.location.href = `/lobby/${roomCode}?username=${username}`;
        }
    });
});