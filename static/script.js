async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        const players = data.players || [];

        document.getElementById('total-players').textContent = players.length;

        const totalGames = players.reduce((sum, p) => sum + p.total_games, 0);
        document.getElementById('total-games').textContent = totalGames;

        const totalWins = players.reduce((sum, p) => sum + p.wins, 0);
        document.getElementById('total-wins').textContent = totalWins;

        const tbody = document.getElementById('leaderboard-body');
        if (players.length === 0){
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No games recorded yet. Send an email to play!</td></tr>';
            return;
        }

        tbody.innerHTML = players.map((p, index) => {
            const emailParts = p.email.split('@');
            const maskedEmail = emailParts[0].length > 3
                ? `${emailParts[0].substring(0, 3)}***@${emailParts[1]}`
                : `*@${emailParts[1]}`;

            return `
                <tr>
                    <td>#${index + 1}</td>
                    <td><strong style="color: #ffffff;">${maskedEmail}</strong></td>
                    <td class="stat-win">${p.wins}</td>
                    <td class="stat-loss">${p.losses}</td>
                    <td>${p.draws}</td>
                    <td>${p.total_games}</td>
                </tr>
            `;        
        }).join('');
    } catch (err) {
        console.error("Failed to load leaderboard stats:", err);
        document.getElementById('leaderboard-body').innerHTML = '<tr><td colspan="6" class="loading">Error loading leaderboard statistics.</td></tr>';
    }
}

fetchStats();