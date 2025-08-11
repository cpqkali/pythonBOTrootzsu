document.addEventListener('DOMContentLoaded', function () {
    const socket = io();

    // --- Bot Status Logic ---
    const botStatusIndicator = document.getElementById('bot-status-indicator');
    const toggleBotBtn = document.getElementById('toggle-bot-btn');

    if (toggleBotBtn) {
        toggleBotBtn.addEventListener('click', () => {
            socket.emit('toggle_bot');
        });
    }

    socket.on('bot_status_update', (data) => {
        if (botStatusIndicator) {
            if (data.running) {
                botStatusIndicator.textContent = 'Bot is Online';
                botStatusIndicator.className = 'badge bg-success';
            } else {
                botStatusIndicator.textContent = 'Bot is Offline';
                botStatusIndicator.className = 'badge bg-danger';
            }
        }
    });

    // --- Admin Panel Editable Tables ---
    document.querySelectorAll('.save-btn').forEach(button => {
        button.addEventListener('click', event => {
            const row = event.target.closest('tr');
            const id = row.dataset.id;
            const data = { id: id };
            
            row.querySelectorAll('[contenteditable="true"]').forEach(cell => {
                const field = cell.dataset.field;
                data[field] = cell.innerText;
            });
            
            // API call to save data
            fetch('/admin/api/service/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    event.target.textContent = 'Saved!';
                    setTimeout(() => { event.target.textContent = 'Save'; }, 2000);
                } else {
                    alert('Error saving data: ' + result.error);
                }
            });
        });
    });
});
