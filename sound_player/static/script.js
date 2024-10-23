document.getElementById('playButton').addEventListener('click', function() {
    fetch('/play')
        .then(response => response.text())
        .then(data => console.log(data))
        .catch(error => console.error('Error:', error));
});