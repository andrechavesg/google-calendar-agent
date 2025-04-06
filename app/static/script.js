const messagesDiv = document.getElementById('messages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.querySelector('#input-area button');
const sessionIdSpan = document.getElementById('session-id');
let ws;
let sessionId = localStorage.getItem('chatSessionId') || generateUUID();
localStorage.setItem('chatSessionId', sessionId);
sessionIdSpan.textContent = sessionId.substring(0, 8); // Display part of the session ID

function generateUUID() { // Public Domain/MIT
    let d = new Date().getTime();//Timestamp
    let d2 = ((typeof performance !== 'undefined') && performance.now && (performance.now()*1000)) || 0;//Time in microseconds since page-load or 0 if unsupported
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        let r = Math.random() * 16;//random number between 0 and 16
        if(d > 0){//Use timestamp until depleted
            r = (d + r)%16 | 0;
            d = Math.floor(d/16);
        } else {//Use microseconds since page-load if supported
            r = (d2 + r)%16 | 0;
            d2 = Math.floor(d2/16);
        }
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    // Include session ID in the WebSocket URL
    const wsUrl = `${wsProtocol}${window.location.host}/ws/${sessionId}`;

    console.log(`Connecting to WebSocket: ${wsUrl}`);
    ws = new WebSocket(wsUrl);

    ws.onopen = function(event) {
        console.log('WebSocket connection opened');
        setButtonState(true); // Enable send button
        addMessage('Connected! How can I help with your calendar today?', 'bot-message');
    };

    ws.onmessage = function(event) {
        console.log('Message from server:', event.data);
        // Simple check to avoid displaying the "Processing" message as a bot response
        if (event.data !== "Processing your request...") {
            addMessage(event.data, 'bot-message');
        }
        setButtonState(true); // Re-enable send button after receiving response
    };

    ws.onerror = function(event) {
        console.error('WebSocket error:', event);
        addMessage('WebSocket connection error. Please try refreshing the page.', 'bot-message error');
        setButtonState(false);
    };

    ws.onclose = function(event) {
        console.log('WebSocket connection closed:', event);
        addMessage('Connection closed. Attempting to reconnect...', 'bot-message error');
        setButtonState(false);
        // Attempt to reconnect after a delay
        setTimeout(connectWebSocket, 5000); // Reconnect every 5 seconds
    };
}

function addMessage(message, type) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', type);
    // Basic sanitization: createTextNode prevents HTML injection
    messageElement.appendChild(document.createTextNode(message));
    messagesDiv.appendChild(messageElement);
    messagesDiv.scrollTop = messagesDiv.scrollHeight; // Scroll to the bottom
}

function setButtonState(enabled) {
    sendButton.disabled = !enabled;
    messageInput.disabled = !enabled;
}

function sendMessage() {
    const message = messageInput.value.trim();
    if (message && ws && ws.readyState === WebSocket.OPEN) {
        addMessage(message, 'user-message');
        ws.send(message);
        messageInput.value = ''; // Clear input field
        setButtonState(false); // Disable button while processing
    } else if (!ws || ws.readyState !== WebSocket.OPEN) {
        addMessage('Cannot send message: Not connected to the server.', 'bot-message error');
    } else if (!message) {
        addMessage('Please type a message first.', 'bot-message error');
    }
}

// --- Event Listeners ---
messageInput.addEventListener('keypress', function(event) {
    if (event.key === 'Enter' && !sendButton.disabled) {
        sendMessage();
    }
});

// Initial setup
setButtonState(false); // Disable button until connected
connectWebSocket();



