let globalStats = { tictactoe: [], minesweeper: [] };
let currentGame = 'tictactoe';

async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        globalStats = await response.json();
        renderDashboard();
    } catch (err) {
        console.error("Failed to load leaderboard stats:", err);
        document.getElementById('leaderboard-body').innerHTML = '<tr><td colspan="6" class="loading">Error loading leaderboard statistics.</td></tr>';
    }
}

function switchGame(game) {
    currentGame = game;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.toLowerCase().replace('-', '').includes(game.replace('-', '')));
    });
    renderDashboard();
}

function renderDashboard() {
    const isMS = currentGame === 'minesweeper';
    const players = globalStats[currentGame] || [];

    document.getElementById('leaderboard-title').textContent = isMS ? "Minesweeper Leaderboard" : "Tic-Tac-Toe Leaderboard";

    // Summary cards
    document.getElementById('total-players').textContent = players.length;
    const totalGames = players.reduce((sum, p) => sum + p.total_games, 0);
    document.getElementById('total-games').textContent = totalGames;
    const totalWins = players.reduce((sum, p) => sum + p.wins, 0);
    document.getElementById('total-wins').textContent = totalWins;

    // Header column change (Minesweeper has no draws)
    const headerRow = document.getElementById('table-header-row');
    if (isMS) {
        headerRow.innerHTML = `
            <th>Rank</th>
            <th>Player</th>
            <th>Wins</th>
            <th>Losses</th>
            <th>Total Games</th>
        `;
    } else {
        headerRow.innerHTML = `
            <th>Rank</th>
            <th>Player</th>
            <th>Wins</th>
            <th>Losses</th>
            <th>Draws</th>
            <th>Total Games</th>
        `;
    }

    const tbody = document.getElementById('leaderboard-body');
    if (players.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${isMS ? 5 : 6}" class="loading">No ${isMS ? 'Minesweeper' : 'Tic-Tac-Toe'} games recorded yet!</td></tr>`;
        return;
    }

    tbody.innerHTML = players.map((p, index) => {
        const emailParts = p.email.split('@');
        const maskedEmail = emailParts[0].length > 3
            ? `${emailParts[0].substring(0, 3)}***@${emailParts[1]}`
            : `*@${emailParts[1]}`;

        if (isMS) {
            return `
                <tr>
                    <td>#${index + 1}</td>
                    <td><strong style="color: #ffffff;">${maskedEmail}</strong></td>
                    <td class="stat-win">${p.wins}</td>
                    <td class="stat-loss">${p.losses}</td>
                    <td>${p.total_games}</td>
                </tr>
            `;
        }

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
}

fetchStats();